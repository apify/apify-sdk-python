from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from apify.storage_clients._apify._key_value_store_client import ApifyKeyValueStoreClient


def _make_kvs_client(
    api_client: AsyncMock | None = None,
    **kwargs: Any,
) -> tuple[ApifyKeyValueStoreClient, AsyncMock]:
    """Create an ApifyKeyValueStoreClient with a mocked API client."""
    if api_client is None:
        api_client = AsyncMock()

    return ApifyKeyValueStoreClient(
        api_client=api_client,
        api_public_base_url='',
        lock=asyncio.Lock(),
        **kwargs,
    ), api_client


async def test_drop_calls_api_delete() -> None:
    """Test that drop() delegates to the API client."""
    client, api_client = _make_kvs_client()
    await client.drop()
    api_client.delete.assert_awaited_once()


async def test_delete_value_calls_api_delete_record() -> None:
    """Test that delete_value() delegates to the API client."""
    client, api_client = _make_kvs_client()
    await client.delete_value(key='my-key')
    api_client.delete_record.assert_awaited_once_with(key='my-key')


async def test_record_exists_delegates_to_api() -> None:
    """Test that record_exists() delegates to the API client."""
    api_client = AsyncMock()
    api_client.record_exists = AsyncMock(return_value=True)
    client, api_client = _make_kvs_client(api_client=api_client)
    result = await client.record_exists(key='existing-key')
    assert result is True
    api_client.record_exists.assert_awaited_once_with(key='existing-key')


async def test_iterate_keys_single_page() -> None:
    """Test iterating keys with a single page of results."""
    api_client = AsyncMock()
    api_client.list_keys = AsyncMock(
        return_value={
            'items': [{'key': 'key1', 'size': 100}, {'key': 'key2', 'size': 200}],
            'count': 2,
            'limit': 1000,
            'isTruncated': False,
            'nextExclusiveStartKey': None,
        }
    )
    client, _ = _make_kvs_client(api_client=api_client)

    keys = [item async for item in client.iterate_keys()]
    assert len(keys) == 2
    assert keys[0].key == 'key1'
    assert keys[1].key == 'key2'


async def test_iterate_keys_with_limit() -> None:
    """Test that iterate_keys respects the limit parameter."""
    api_client = AsyncMock()
    api_client.list_keys = AsyncMock(
        return_value={
            'items': [{'key': f'key{i}', 'size': 100} for i in range(5)],
            'count': 5,
            'limit': 1000,
            'isTruncated': True,
            'nextExclusiveStartKey': 'key4',
        }
    )
    client, _ = _make_kvs_client(api_client=api_client)

    keys = [item async for item in client.iterate_keys(limit=3)]
    assert len(keys) == 3


async def test_iterate_keys_pagination() -> None:
    """Test that iterate_keys handles pagination across multiple pages."""
    page1 = {
        'items': [{'key': 'key1', 'size': 100}],
        'count': 1,
        'limit': 1000,
        'isTruncated': True,
        'nextExclusiveStartKey': 'key1',
    }
    page2 = {
        'items': [{'key': 'key2', 'size': 200}],
        'count': 1,
        'limit': 1000,
        'isTruncated': False,
        'nextExclusiveStartKey': None,
    }
    api_client = AsyncMock()
    api_client.list_keys = AsyncMock(side_effect=[page1, page2])
    client, _ = _make_kvs_client(api_client=api_client)

    keys = [item async for item in client.iterate_keys()]
    assert len(keys) == 2
    assert keys[0].key == 'key1'
    assert keys[1].key == 'key2'
    assert api_client.list_keys.await_count == 2


async def test_purge_raises_not_implemented() -> None:
    """Test that purge() raises NotImplementedError."""
    client, _ = _make_kvs_client()
    with pytest.raises(NotImplementedError, match='Purging key-value stores is not supported'):
        await client.purge()


async def test_deprecated_api_public_base_url() -> None:
    """Test that passing api_public_base_url triggers deprecation warning."""
    api_client = AsyncMock()
    with pytest.warns(DeprecationWarning, match='api_public_base_url argument is deprecated'):
        ApifyKeyValueStoreClient(
            api_client=api_client,
            api_public_base_url='https://api.apify.com',
            lock=asyncio.Lock(),
        )
