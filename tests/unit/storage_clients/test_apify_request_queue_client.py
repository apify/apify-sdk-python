from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from apify_client._models_generated import RequestQueueHead
from crawlee.storage_clients.models import RequestQueueMetadata

from apify.storage_clients._apify._request_queue_single_client import ApifyRequestQueueSingleClient
from apify.storage_clients._apify._utils import unique_key_to_request_id


def _make_single_client(
    api_client: AsyncMock | None = None,
) -> tuple[ApifyRequestQueueSingleClient, AsyncMock]:
    if api_client is None:
        api_client = AsyncMock()
    now = datetime.now(tz=UTC)
    metadata = RequestQueueMetadata(
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
    client = ApifyRequestQueueSingleClient(api_client=api_client, metadata=metadata, cache_size=100)
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
