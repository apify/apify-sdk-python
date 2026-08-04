from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, Mock

import pytest

from crawlee._utils.byte_size import ByteSize

from apify.storage_clients._apify._dataset_client import ApifyDatasetClient


def _make_dataset_client(api_client: AsyncMock | None = None) -> tuple[ApifyDatasetClient, AsyncMock]:
    """Create an ApifyDatasetClient with a mocked API client."""
    if api_client is None:
        api_client = AsyncMock()

    return ApifyDatasetClient(
        api_client=api_client,
        lock=asyncio.Lock(),
    ), api_client


async def test_purge_raises_not_implemented() -> None:
    """Test that purge() raises NotImplementedError."""
    client, _ = _make_dataset_client()
    with pytest.raises(NotImplementedError, match='Purging datasets is not supported'):
        await client.purge()


async def test_drop_calls_api_delete() -> None:
    """Test that drop() delegates to the API client."""
    client, api_client = _make_dataset_client()
    await client.drop()
    api_client.delete.assert_awaited_once()


async def test_push_data_sends_compact_json() -> None:
    """Pushed payloads carry no indentation or separator padding."""
    client, api_client = _make_dataset_client()

    await client.push_data([{'id': 1, 'name': 'first'}, {'id': 2, 'name': 'second'}])

    chunk = api_client.push_items.await_args.kwargs['items']
    assert chunk == '[{"id":1,"name":"first"},{"id":2,"name":"second"}]'


async def test_push_data_serializes_in_a_single_thread_hop_per_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Serialization is offloaded once per pushed chunk rather than once per item."""
    monkeypatch.setattr(ApifyDatasetClient, '_EFFECTIVE_LIMIT_SIZE', ByteSize(200))
    to_thread = Mock(wraps=asyncio.to_thread)
    monkeypatch.setattr(asyncio, 'to_thread', to_thread)
    client, api_client = _make_dataset_client()

    await client.push_data([{'id': i} for i in range(500)])

    assert api_client.push_items.await_count > 1
    assert to_thread.call_count == api_client.push_items.await_count


async def test_push_data_makes_progress_when_an_item_fills_a_whole_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    """An item that fits the limit only without the array wrapper still yields one chunk per item."""
    items = [{'value': 'x' * 30} for _ in range(3)]
    payloads = [json.dumps(item, ensure_ascii=False, separators=(',', ':')) for item in items]
    monkeypatch.setattr(ApifyDatasetClient, '_EFFECTIVE_LIMIT_SIZE', ByteSize(len(payloads[0].encode('utf-8'))))
    client, api_client = _make_dataset_client()

    async with asyncio.timeout(5):
        await client.push_data(items)

    chunks = [call.kwargs['items'] for call in api_client.push_items.await_args_list]
    assert chunks == [f'[{payload}]' for payload in payloads]


async def test_push_data_splits_items_into_chunks_within_the_size_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Items are pushed in several chunks, each staying within the payload size limit."""
    monkeypatch.setattr(ApifyDatasetClient, '_EFFECTIVE_LIMIT_SIZE', ByteSize(100))
    client, api_client = _make_dataset_client()
    items = [{'value': 'x' * 30} for _ in range(5)]

    await client.push_data(items)

    chunks = [call.kwargs['items'] for call in api_client.push_items.await_args_list]
    assert len(chunks) > 1
    assert all(len(chunk.encode('utf-8')) <= 100 for chunk in chunks)
    assert [item for chunk in chunks for item in json.loads(chunk)] == items


async def test_push_data_rejects_an_oversized_item(monkeypatch: pytest.MonkeyPatch) -> None:
    """An item exceeding the payload size limit raises with its index."""
    monkeypatch.setattr(ApifyDatasetClient, '_EFFECTIVE_LIMIT_SIZE', ByteSize(100))
    client, _ = _make_dataset_client()

    with pytest.raises(ValueError, match='at index 1 is too large'):
        await client.push_data([{'id': 1}, {'value': 'x' * 200}])


async def test_push_data_rejects_a_non_serializable_item() -> None:
    """An item that cannot be serialized to JSON raises with its index."""
    client, _ = _make_dataset_client()
    circular: dict = {}
    circular['self'] = circular

    with pytest.raises(ValueError, match='at index 0 is not serializable'):
        await client.push_data(circular)
