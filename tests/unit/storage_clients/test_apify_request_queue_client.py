from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from apify_client._models import Request as ClientRequest
from apify_client._models import RequestQueueHead, RequestQueueStats, RequestRegistration
from crawlee.storage_clients.models import RequestQueueMetadata

from apify import Request
from apify.storage_clients._apify._models import ApifyRequestQueueMetadata
from apify.storage_clients._apify._request_queue_shared_client import ApifyRequestQueueSharedClient
from apify.storage_clients._apify._request_queue_single_client import ApifyRequestQueueSingleClient
from apify.storage_clients._apify._utils import unique_key_to_request_id

if TYPE_CHECKING:
    from collections.abc import Callable


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
    client = ApifyRequestQueueSharedClient(
        api_client=api_client,
        metadata=_make_metadata(),
        cache_size=100,
        metadata_getter=AsyncMock(),
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


async def test_fetch_next_request_skips_already_handled() -> None:
    """A request the platform reports as already handled must not be returned by `fetch_next_request`."""
    client, api_client = _make_single_client()

    unique_key = 'https://example.com'
    request_id = unique_key_to_request_id(unique_key)

    # Head reconciliation returns nothing new.
    api_client.list_head = AsyncMock(
        return_value=RequestQueueHead(
            limit=200,
            queue_modified_at=datetime.now(tz=UTC),
            had_multiple_clients=False,
            items=[],
        )
    )
    # The platform reports this request as already handled.
    api_client.get_request = AsyncMock(
        return_value=ClientRequest.model_validate(
            {
                'id': request_id,
                'uniqueKey': unique_key,
                'url': unique_key,
                'method': 'GET',
                'headers': {},
                'userData': {},
                'retryCount': 0,
                'noRetry': False,
                'handledAt': datetime.now(tz=UTC),
            }
        )
    )

    # Seed the local head estimate with the request id.
    client._head_requests.append(request_id)

    result = await client.fetch_next_request()

    assert result is None, 'Already-handled request must not be fetched.'
    assert request_id not in client._requests_in_progress, 'Handled request must not be left in progress.'
    assert request_id in client._requests_already_handled, 'Handled request id should be cached for deduplication.'


@pytest.mark.parametrize(
    'make_client',
    [_make_single_client, _make_shared_client],
    ids=['single_client', 'shared_client'],
)
async def test_reclaim_previously_handled_adjusts_counts(
    make_client: Callable[[], tuple[ApifyRequestQueueSingleClient | ApifyRequestQueueSharedClient, AsyncMock]],
) -> None:
    """Reclaiming a previously handled request must move it from handled back to pending in the metadata."""
    client, api_client = make_client()
    client.metadata.handled_request_count = 1
    client.metadata.pending_request_count = 0

    unique_key = 'https://example.com'
    request_id = unique_key_to_request_id(unique_key)
    request = Request.from_url(unique_key, unique_key=unique_key)
    request.handled_at = datetime.now(tz=UTC)

    # After reclaiming, the platform reports the request as no longer handled.
    api_client.update_request = AsyncMock(
        return_value=RequestRegistration.model_validate(
            {'requestId': request_id, 'wasAlreadyPresent': True, 'wasAlreadyHandled': False}
        )
    )

    await client.reclaim_request(request)

    assert client.metadata.handled_request_count == 0, 'Reclaimed request must be removed from the handled count.'
    assert client.metadata.pending_request_count == 1, 'Reclaimed request must be added back to the pending count.'
