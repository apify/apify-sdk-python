from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from apify_client._models import AddedRequest, BatchAddResult, RequestQueueHead, RequestQueueStats
from crawlee.storage_clients.models import RequestQueueMetadata

from apify import Request
from apify.storage_clients._apify._models import ApifyRequestQueueMetadata
from apify.storage_clients._apify._request_queue_shared_client import ApifyRequestQueueSharedClient
from apify.storage_clients._apify._request_queue_single_client import ApifyRequestQueueSingleClient
from apify.storage_clients._apify._utils import unique_key_to_request_id

if TYPE_CHECKING:
    from collections.abc import Sequence


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


def _batch_result_all_processed(requests: Sequence[Request]) -> BatchAddResult:
    """Build a `batch_add_requests` response marking every request as newly processed."""
    return BatchAddResult.model_construct(
        processed_requests=[
            AddedRequest.model_construct(
                request_id=unique_key_to_request_id(request.unique_key),
                unique_key=request.unique_key,
                was_already_present=False,
                was_already_handled=False,
            )
            for request in requests
        ],
        unprocessed_requests=[],
    )


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


# Failed `batch_add_requests` must not poison the local dedup cache (otherwise a user retry is
# silently deduplicated and the request never reaches the platform).


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
