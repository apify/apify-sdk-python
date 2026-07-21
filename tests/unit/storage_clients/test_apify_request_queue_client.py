from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from apify_client._models import (
    AddedRequest,
    BatchAddResult,
    LockedHeadRequest,
    LockedRequestQueueHead,
    RequestDraft,
    RequestLockInfo,
    RequestQueueHead,
    RequestQueueStats,
)
from apify_client._models import Request as ClientRequest
from crawlee.storage_clients.models import AddRequestsResponse, ProcessedRequest, RequestQueueMetadata

from apify import Request
from apify.storage_clients._apify._models import ApifyRequestQueueMetadata
from apify.storage_clients._apify._request_queue_shared_client import ApifyRequestQueueSharedClient
from apify.storage_clients._apify._request_queue_single_client import ApifyRequestQueueSingleClient
from apify.storage_clients._apify._utils import unique_key_to_request_id

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


def _make_metadata() -> RequestQueueMetadata:
    now = datetime.now(tz=UTC)
    return RequestQueueMetadata(
        id='test-rq-id',
        name='test-rq',
        accessed_at=now,
        created_at=now,
        modified_at=now,
        had_multiple_clients=False,
        handled_request_count=0,
        pending_request_count=0,
        total_request_count=0,
    )


def _batch_result(
    *,
    processed: Sequence[Request] = (),
    unprocessed: Sequence[Request] = (),
) -> BatchAddResult:
    """Build a `batch_add_requests` response with explicit processed / unprocessed splits."""
    return BatchAddResult.model_construct(
        processed_requests=[
            AddedRequest.model_construct(
                request_id=unique_key_to_request_id(request.unique_key),
                unique_key=request.unique_key,
                was_already_present=False,
                was_already_handled=False,
            )
            for request in processed
        ],
        unprocessed_requests=[
            RequestDraft.model_construct(
                unique_key=request.unique_key,
                url=request.url,
                method=request.method,
            )
            for request in unprocessed
        ],
    )


def _batch_result_all_processed(requests: Sequence[Request]) -> BatchAddResult:
    """Build a `batch_add_requests` response marking every request as newly processed."""
    return _batch_result(processed=requests)


def _make_single_client(
    api_client: AsyncMock | None = None,
) -> tuple[ApifyRequestQueueSingleClient, AsyncMock]:
    if api_client is None:
        api_client = AsyncMock()
    client = ApifyRequestQueueSingleClient(api_client=api_client, metadata=_make_metadata(), cache_size=100)
    return client, api_client


def _make_shared_client(
    api_client: AsyncMock | None = None,
) -> tuple[ApifyRequestQueueSharedClient, AsyncMock]:
    if api_client is None:
        api_client = AsyncMock()
    metadata = _make_metadata()
    client = ApifyRequestQueueSharedClient(
        api_client=api_client,
        metadata=metadata,
        cache_size=100,
        metadata_getter=AsyncMock(return_value=metadata),
    )
    return client, api_client


def test_unique_key_to_request_id_length() -> None:
    unique_key = 'exampleKey123'
    request_id = unique_key_to_request_id(unique_key, request_id_length=15)
    assert len(request_id) == 15, 'Request ID should have the correct length.'


def test_unique_key_to_request_id_consistency() -> None:
    unique_key = 'consistentKey'
    request_id_1 = unique_key_to_request_id(unique_key)
    request_id_2 = unique_key_to_request_id(unique_key)
    assert request_id_1 == request_id_2, 'The same unique key should generate consistent request IDs.'


@pytest.mark.parametrize(
    ('stats', 'expected_read_count'),
    [(None, None), ({'readCount': 5}, 5)],
    ids=['none_coerced_to_default', 'populated_passed_through'],
)
def test_metadata_stats_validation(stats: dict | None, expected_read_count: int | None) -> None:
    """A `stats: None` payload (as `open()` produces via `model_dump`) defaults; a populated one passes through."""
    now = datetime.now(tz=UTC)
    metadata = ApifyRequestQueueMetadata.model_validate(
        {
            'id': 'test-rq-id',
            'name': None,
            'accessedAt': now,
            'createdAt': now,
            'modifiedAt': now,
            'hadMultipleClients': False,
            'handledRequestCount': 0,
            'pendingRequestCount': 0,
            'totalRequestCount': 0,
            'stats': stats,
        }
    )
    assert isinstance(metadata.stats, RequestQueueStats)
    assert metadata.stats.read_count == expected_read_count


@pytest.mark.parametrize(
    ('unique_key', 'expected_request_id'),
    [
        ('abc', 'ungWv48BzpBQUDe'),
        ('uniqueKey', 'xiWPs083cree7mH'),
        ('', '47DEQpj8HBSaTIm'),
        ('测试中文', 'lKPdJkdvw8MXEUp'),
        ('test+/=', 'XZRQjhoG0yjfnYD'),
    ],
    ids=[
        'basic_abc',
        'keyword_uniqueKey',
        'empty_string',
        'non_ascii_characters',
        'url_unsafe_characters',
    ],
)
def test_unique_key_to_request_id_matches_known_values(unique_key: str, expected_request_id: str) -> None:
    request_id = unique_key_to_request_id(unique_key)
    assert request_id == expected_request_id, f'Unique key "{unique_key}" should produce the expected request ID.'


@pytest.mark.parametrize(
    ('in_progress_count', 'expected_limit'),
    [
        (0, 200),
        (300, 500),
        (900, ApifyRequestQueueSingleClient._MAX_HEAD_ITEMS),
    ],
    ids=['no_in_progress', 'pads_by_in_progress', 'caps_at_max_head_items'],
)
async def test_list_head_limit(in_progress_count: int, expected_limit: int) -> None:
    client, api_client = _make_single_client()
    api_client.list_head = AsyncMock(
        return_value=RequestQueueHead(
            limit=expected_limit,
            queue_modified_at=datetime.now(tz=UTC),
            had_multiple_clients=False,
            items=[],
        )
    )
    client._requests_in_progress = {f'req_{i}' for i in range(in_progress_count)}

    await client._list_head()

    api_client.list_head.assert_awaited_once_with(limit=expected_limit)


# Adding a request through `batch_add_requests` must never poison the local dedup cache or report false
# success. A failed add leaves nothing cached, so a later add (sequential or concurrent) still reaches the
# platform; a concurrent producer of the same request deduplicates against the in-flight add instead of
# re-sending it, yet is only told the request is present once the platform actually accepts it.


@pytest.mark.parametrize('access', ['single', 'shared'])
async def test_failed_batch_add_does_not_poison_dedup_cache(access: str) -> None:
    """A failed `batch_add_requests` leaves no cached entry, so a retry still reaches the platform."""
    client, api_client = _make_single_client() if access == 'single' else _make_shared_client()
    # The single client lazily initializes its caches via `list_requests`; harmless for the shared client.
    api_client.list_requests = AsyncMock(return_value=SimpleNamespace(items=[]))
    request = Request.from_url('https://example.com/1')
    request_id = unique_key_to_request_id(request.unique_key)

    # First attempt: the platform call fails.
    api_client.batch_add_requests = AsyncMock(side_effect=RuntimeError('network down'))
    with pytest.raises(RuntimeError):
        await client.add_batch_of_requests([request])
    assert request_id not in client._requests_cache

    # Retry: the platform call succeeds. The request must be sent again, not deduped away.
    api_client.batch_add_requests = AsyncMock(return_value=_batch_result_all_processed([request]))
    await client.add_batch_of_requests([request])

    api_client.batch_add_requests.assert_awaited_once()
    assert api_client.batch_add_requests.await_args is not None
    assert len(api_client.batch_add_requests.await_args.kwargs['requests']) == 1


async def _start_first_then_concurrent_producer(
    client: ApifyRequestQueueSingleClient | ApifyRequestQueueSharedClient,
    request: Request,
    *,
    in_flight: asyncio.Event,
) -> tuple[asyncio.Task[AddRequestsResponse], asyncio.Task[AddRequestsResponse]]:
    """Start one producer, wait until its `batch_add_requests` is in flight, then start a concurrent producer
    of the same request and let it park on the in-flight add. Returns the (first, second) tasks."""
    if isinstance(client, ApifyRequestQueueSingleClient):
        # Skip the lazy `list_requests` init so the concurrent producer's only suspension point is the
        # in-flight future, which makes the scheduling below deterministic.
        client._initialized_caches = True

    first = asyncio.create_task(client.add_batch_of_requests([request]))
    await in_flight.wait()
    second = asyncio.create_task(client.add_batch_of_requests([request]))
    await asyncio.sleep(0)  # let the concurrent producer classify and park on the in-flight future
    return first, second


@pytest.mark.parametrize('access', ['single', 'shared'])
async def test_concurrent_add_failure_does_not_falsely_dedupe(access: str) -> None:
    """While one producer's `batch_add_requests` is in flight and then fails, a concurrent producer of the same
    request must not report false success: the request is returned unprocessed (so the caller retries it)."""
    client, api_client = _make_single_client() if access == 'single' else _make_shared_client()
    request = Request.from_url('https://example.com/1')
    request_id = unique_key_to_request_id(request.unique_key)

    in_flight = asyncio.Event()
    release = asyncio.Event()
    call_count = 0

    async def batch_add(*, requests: list, forefront: bool = False) -> BatchAddResult:  # noqa: ARG001
        nonlocal call_count
        call_count += 1
        in_flight.set()
        await release.wait()
        raise RuntimeError('network down')

    api_client.batch_add_requests = AsyncMock(side_effect=batch_add)

    first, second = await _start_first_then_concurrent_producer(client, request, in_flight=in_flight)

    # Nothing is committed while the first call is still in flight, so the concurrent producer cannot observe a
    # false "already present" entry.
    assert request_id not in client._requests_cache

    # Let the first producer fail.
    release.set()
    with pytest.raises(RuntimeError):
        await first

    # The concurrent producer deduplicated against the in-flight add (no second API call), but because that add
    # failed it must be told the request is unprocessed rather than receiving false success.
    response = await second
    assert call_count == 1
    assert [unprocessed.unique_key for unprocessed in response.unprocessed_requests] == [request.unique_key]
    assert all(processed.unique_key != request.unique_key for processed in response.processed_requests)
    assert request_id not in client._requests_cache


@pytest.mark.parametrize('access', ['single', 'shared'])
async def test_concurrent_add_deduplicates_against_in_flight(access: str) -> None:
    """A concurrent producer of an in-flight request deduplicates against it: only one `batch_add_requests` call
    is made, and once it succeeds the concurrent producer is told the request is already present."""
    client, api_client = _make_single_client() if access == 'single' else _make_shared_client()
    request = Request.from_url('https://example.com/1')
    request_id = unique_key_to_request_id(request.unique_key)

    in_flight = asyncio.Event()
    release = asyncio.Event()
    call_count = 0

    async def batch_add(*, requests: list, forefront: bool = False) -> BatchAddResult:  # noqa: ARG001
        nonlocal call_count
        call_count += 1
        in_flight.set()
        await release.wait()
        return _batch_result_all_processed([request])

    api_client.batch_add_requests = AsyncMock(side_effect=batch_add)

    first, second = await _start_first_then_concurrent_producer(client, request, in_flight=in_flight)

    # Let the first producer succeed.
    release.set()
    first_response = await first
    second_response = await second

    assert call_count == 1
    assert request_id in client._requests_cache
    # The first producer added the request, the concurrent one deduplicated against the in-flight add.
    assert [processed.unique_key for processed in first_response.processed_requests] == [request.unique_key]
    assert [processed.unique_key for processed in second_response.processed_requests] == [request.unique_key]
    assert second_response.processed_requests[0].was_already_present is True
    assert second_response.unprocessed_requests == []


@pytest.mark.parametrize('access', ['single', 'shared'])
async def test_partial_unprocessed_commits_only_accepted_requests(access: str) -> None:
    """When the platform accepts only part of a batch, only the accepted requests are cached. The rejected one
    leaves no entry behind, so a later retry re-sends it while the accepted one is deduped locally."""
    client, api_client = _make_single_client() if access == 'single' else _make_shared_client()
    api_client.list_requests = AsyncMock(return_value=SimpleNamespace(items=[]))
    accepted = Request.from_url('https://example.com/accepted')
    rejected = Request.from_url('https://example.com/rejected')
    accepted_id = unique_key_to_request_id(accepted.unique_key)
    rejected_id = unique_key_to_request_id(rejected.unique_key)

    api_client.batch_add_requests = AsyncMock(return_value=_batch_result(processed=[accepted], unprocessed=[rejected]))
    response = await client.add_batch_of_requests([accepted, rejected])

    # Only the accepted request is committed to the local cache; the rejected one is not.
    assert accepted_id in client._requests_cache
    assert rejected_id not in client._requests_cache
    # The response mirrors the platform split, and no in-flight marker is left behind.
    assert [processed.unique_key for processed in response.processed_requests] == [accepted.unique_key]
    assert [unprocessed.unique_key for unprocessed in response.unprocessed_requests] == [rejected.unique_key]
    assert client._requests_being_added == {}

    # Retry both: the rejected request must reach the platform again (it was not poisoned), while the accepted one
    # is deduped locally and never re-sent.
    api_client.batch_add_requests = AsyncMock(return_value=_batch_result(processed=[rejected]))
    await client.add_batch_of_requests([accepted, rejected])

    api_client.batch_add_requests.assert_awaited_once()
    assert api_client.batch_add_requests.await_args is not None
    resent = api_client.batch_add_requests.await_args.kwargs['requests']
    assert [request['uniqueKey'] for request in resent] == [rejected.unique_key]


def _locked_item(request: Request, *, lock_expires_at: datetime) -> LockedHeadRequest:
    """Build a single locked head entry for `request` with the given lock expiry."""
    return LockedHeadRequest(
        id=unique_key_to_request_id(request.unique_key),
        unique_key=request.unique_key,
        url=request.url,
        method=request.method,
        retry_count=0,
        lock_expires_at=lock_expires_at,
    )


def _locked_head(
    items: Sequence[LockedHeadRequest],
    *,
    queue_has_locked_requests: bool = True,
) -> LockedRequestQueueHead:
    """Build a `list_and_lock_head` response wrapping the given locked entries."""
    return LockedRequestQueueHead(
        limit=25,
        queue_modified_at=datetime.now(tz=UTC),
        queue_has_locked_requests=queue_has_locked_requests,
        had_multiple_clients=True,
        lock_secs=180,
        items=list(items),
    )


def _processed(request: Request, *, was_already_handled: bool = False) -> ProcessedRequest:
    """Build the `update_request` result returned by the API for a handled or reclaimed request."""
    return ProcessedRequest(
        id=unique_key_to_request_id(request.unique_key),
        unique_key=request.unique_key,
        was_already_present=True,
        was_already_handled=was_already_handled,
    )


def _client_request(request: Request) -> ClientRequest:
    """Build the API client's `Request` returned by `get_request` for a hydrated fetch."""
    return ClientRequest(
        id=unique_key_to_request_id(request.unique_key),
        unique_key=request.unique_key,
        url=request.url,
        method=request.method,
        headers={},
        user_data={},
        retry_count=0,
        no_retry=False,
        handled_at=None,
    )


def _client_request_getter(requests: Sequence[Request]) -> Callable[[str], ClientRequest]:
    """Build a `get_request` side effect mapping request IDs back to their API client `Request`."""
    by_id = {unique_key_to_request_id(request.unique_key): _client_request(request) for request in requests}
    return lambda request_id: by_id[request_id]


async def test_fetch_next_request_prolongs_lock() -> None:
    """Handing a request to a consumer prolongs its lock, so a handler slower than the initial lock is still safe."""
    client, api_client = _make_shared_client()
    request = Request.from_url('https://example.com/1')
    request_id = unique_key_to_request_id(request.unique_key)
    future = datetime.now(tz=UTC) + timedelta(seconds=180)

    api_client.list_and_lock_head = AsyncMock(
        return_value=_locked_head([_locked_item(request, lock_expires_at=future)])
    )
    api_client.get_request = AsyncMock(return_value=_client_request(request))
    api_client.prolong_request_lock = AsyncMock(return_value=RequestLockInfo(lock_expires_at=future))

    fetched = await client.fetch_next_request()

    assert fetched is not None
    assert fetched.unique_key == request.unique_key
    api_client.prolong_request_lock.assert_awaited_once()
    assert api_client.prolong_request_lock.await_args is not None
    assert api_client.prolong_request_lock.await_args.args[0] == request_id


async def test_fetch_next_request_skips_expired_lock() -> None:
    """A queued head entry whose lock already lapsed is skipped in favour of the next entry with a live lock."""
    client, api_client = _make_shared_client()
    expired = Request.from_url('https://example.com/expired')
    valid = Request.from_url('https://example.com/valid')
    now = datetime.now(tz=UTC)

    api_client.list_and_lock_head = AsyncMock(
        return_value=_locked_head(
            [
                _locked_item(expired, lock_expires_at=now - timedelta(seconds=60)),
                _locked_item(valid, lock_expires_at=now + timedelta(seconds=180)),
            ]
        )
    )
    api_client.get_request = AsyncMock(side_effect=_client_request_getter([expired, valid]))
    api_client.prolong_request_lock = AsyncMock(
        return_value=RequestLockInfo(lock_expires_at=now + timedelta(seconds=180))
    )

    fetched = await client.fetch_next_request()

    assert fetched is not None
    assert fetched.unique_key == valid.unique_key
    # Only the live-lock request is prolonged; the expired one is skipped rather than re-processed.
    api_client.prolong_request_lock.assert_awaited_once()
    assert api_client.prolong_request_lock.await_args is not None
    assert api_client.prolong_request_lock.await_args.args[0] == unique_key_to_request_id(valid.unique_key)


async def test_fetch_next_request_does_not_rehand_in_progress() -> None:
    """A request already in progress is not handed out again even if the platform re-lists it after a lock lapse."""
    client, api_client = _make_shared_client()
    request = Request.from_url('https://example.com/1')
    future = datetime.now(tz=UTC) + timedelta(seconds=180)

    # The platform keeps returning the same locked request on every head listing.
    api_client.list_and_lock_head = AsyncMock(
        return_value=_locked_head([_locked_item(request, lock_expires_at=future)])
    )
    api_client.get_request = AsyncMock(return_value=_client_request(request))
    api_client.prolong_request_lock = AsyncMock(return_value=RequestLockInfo(lock_expires_at=future))

    first = await client.fetch_next_request()
    second = await client.fetch_next_request()

    assert first is not None
    assert first.unique_key == request.unique_key
    assert second is None


async def test_fetch_next_request_skips_when_lock_prolong_fails() -> None:
    """A request whose lock cannot be prolonged is skipped and released, so a later fetch can still hand it out."""
    client, api_client = _make_shared_client()
    request = Request.from_url('https://example.com/1')
    future = datetime.now(tz=UTC) + timedelta(seconds=180)

    api_client.list_and_lock_head = AsyncMock(
        return_value=_locked_head([_locked_item(request, lock_expires_at=future)])
    )
    api_client.get_request = AsyncMock(return_value=_client_request(request))
    api_client.prolong_request_lock = AsyncMock(
        side_effect=[RuntimeError('lock lost'), RequestLockInfo(lock_expires_at=future)]
    )

    first = await client.fetch_next_request()
    second = await client.fetch_next_request()

    assert first is None
    assert second is not None
    assert second.unique_key == request.unique_key


async def test_fetch_next_request_skips_when_lock_not_reacquired() -> None:
    """A `None` from `prolong_request_lock` (lock not re-acquired) is a skip, not a successful hand-out."""
    client, api_client = _make_shared_client()
    request = Request.from_url('https://example.com/1')
    future = datetime.now(tz=UTC) + timedelta(seconds=180)

    api_client.list_and_lock_head = AsyncMock(
        return_value=_locked_head([_locked_item(request, lock_expires_at=future)])
    )
    api_client.get_request = AsyncMock(return_value=_client_request(request))
    # First call reports the lock as not (re)acquired via a `None` return; the second re-acquires it.
    api_client.prolong_request_lock = AsyncMock(side_effect=[None, RequestLockInfo(lock_expires_at=future)])

    first = await client.fetch_next_request()
    second = await client.fetch_next_request()

    assert first is None
    assert second is not None
    assert second.unique_key == request.unique_key


async def test_is_finished_false_while_request_in_progress() -> None:
    """`is_finished` stays False while a fetched request is still in progress, even if the head lists empty."""
    client, api_client = _make_shared_client()
    request = Request.from_url('https://example.com/1')
    future = datetime.now(tz=UTC) + timedelta(seconds=180)

    api_client.list_and_lock_head = AsyncMock(
        side_effect=[
            _locked_head([_locked_item(request, lock_expires_at=future)]),
            # The in-progress request is locked, so the platform head lists empty and reports no locked requests.
            _locked_head([], queue_has_locked_requests=False),
        ]
    )
    api_client.get_request = AsyncMock(return_value=_client_request(request))
    api_client.prolong_request_lock = AsyncMock(return_value=RequestLockInfo(lock_expires_at=future))

    fetched = await client.fetch_next_request()

    assert fetched is not None
    # The request is handed out but not yet handled or reclaimed, so the queue is not finished.
    assert await client.is_finished() is False


async def test_mark_request_as_handled_clears_in_progress() -> None:
    """Marking a fetched request handled stops tracking it as in progress, so the queue can finish."""
    client, api_client = _make_shared_client()
    request = Request.from_url('https://example.com/1')
    request_id = unique_key_to_request_id(request.unique_key)
    future = datetime.now(tz=UTC) + timedelta(seconds=180)

    api_client.list_and_lock_head = AsyncMock(
        return_value=_locked_head([_locked_item(request, lock_expires_at=future)])
    )
    api_client.get_request = AsyncMock(return_value=_client_request(request))
    api_client.prolong_request_lock = AsyncMock(return_value=RequestLockInfo(lock_expires_at=future))
    api_client.update_request = AsyncMock(return_value=_processed(request))

    fetched = await client.fetch_next_request()

    assert fetched is not None
    assert request_id in client._requests_in_progress

    await client.mark_request_as_handled(fetched)

    assert request_id not in client._requests_in_progress


async def test_reclaim_request_frees_in_progress() -> None:
    """Reclaiming a fetched request stops tracking it as in progress so it can be handed out again."""
    client, api_client = _make_shared_client()
    request = Request.from_url('https://example.com/1')
    request_id = unique_key_to_request_id(request.unique_key)
    future = datetime.now(tz=UTC) + timedelta(seconds=180)

    api_client.list_and_lock_head = AsyncMock(
        return_value=_locked_head([_locked_item(request, lock_expires_at=future)])
    )
    api_client.get_request = AsyncMock(return_value=_client_request(request))
    api_client.prolong_request_lock = AsyncMock(return_value=RequestLockInfo(lock_expires_at=future))
    api_client.update_request = AsyncMock(return_value=_processed(request))

    first = await client.fetch_next_request()

    assert first is not None
    assert request_id in client._requests_in_progress

    await client.reclaim_request(first)

    assert request_id not in client._requests_in_progress

    # After reclaim the same request is eligible to be handed out again.
    second = await client.fetch_next_request()

    assert second is not None
    assert second.unique_key == request.unique_key
