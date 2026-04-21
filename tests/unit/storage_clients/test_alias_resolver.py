from __future__ import annotations

from unittest.mock import AsyncMock, patch

from apify._configuration import Configuration
from apify.storage_clients._apify._alias_resolving import AliasResolver


def test_storage_key_format() -> None:
    """Test that _storage_key has the expected format: type,alias,hash."""
    config = Configuration(token='test-token', api_base_url='https://api.apify.com')
    resolver = AliasResolver(storage_type='Dataset', alias='my-alias', configuration=config)
    key = resolver._storage_key
    parts = key.split(',')
    assert len(parts) == 3
    assert parts[0] == 'Dataset'
    assert parts[1] == 'my-alias'
    assert len(parts[2]) > 0  # hash should be non-empty


async def test_resolve_id_returns_none_for_unknown() -> None:
    """Test that resolve_id returns None for an alias not in the map."""
    AliasResolver._alias_map = {}
    config = Configuration(token='test-token')
    resolver = AliasResolver(storage_type='Dataset', alias='unknown-alias', configuration=config)
    result = await resolver.resolve_id()
    assert result is None


async def test_resolve_id_returns_stored_id() -> None:
    """Test that resolve_id returns the ID if it was previously stored."""
    config = Configuration(token='test-token', api_base_url='https://api.apify.com')
    resolver = AliasResolver(storage_type='KeyValueStore', alias='test-alias', configuration=config)
    storage_key = resolver._storage_key
    AliasResolver._alias_map = {storage_key: 'stored-id-123'}

    result = await resolver.resolve_id()
    assert result == 'stored-id-123'


async def test_store_mapping_local_only() -> None:
    """Test that store_mapping only updates in-memory map when not at home."""
    AliasResolver._alias_map = {}
    config = Configuration(is_at_home=False, token='test-token')
    resolver = AliasResolver(storage_type='RequestQueue', alias='test-alias', configuration=config)

    await resolver.store_mapping(storage_id='new-id-456')

    # Verify the mapping was stored in memory
    assert AliasResolver._alias_map[resolver._storage_key] == 'new-id-456'


async def test_concurrent_alias_creation_uses_lock() -> None:
    """Test that the context manager acquires and releases a lock."""
    AliasResolver._alias_init_lock = None
    AliasResolver._alias_map = {}
    config = Configuration(token='test-token')
    resolver = AliasResolver(storage_type='Dataset', alias='test', configuration=config)

    async with resolver:
        # Lock should be acquired
        lock = await AliasResolver._get_alias_init_lock()
        assert lock.locked()

    # Lock should be released after exiting
    lock = await AliasResolver._get_alias_init_lock()
    assert not lock.locked()


async def test_get_alias_map_returns_in_memory_map() -> None:
    """Test that _get_alias_map returns the in-memory map when not at home."""
    AliasResolver._alias_map = {'existing_key': 'existing_id'}
    config = Configuration(is_at_home=False, token='test-token')

    result = await AliasResolver._get_alias_map(config)
    assert result == {'existing_key': 'existing_id'}
    # Also verify that an empty map is returned without fetching from KVS when not at home
    AliasResolver._alias_map = {}
    result = await AliasResolver._get_alias_map(config)
    assert result == {}


async def test_get_alias_map_loads_from_kvs_only_once_when_empty() -> None:
    """An empty KVS response must not trigger repeat fetches on subsequent calls."""
    config = Configuration(is_at_home=True, token='test-token', default_key_value_store_id='default-kvs-id')

    fake_kvs_client = AsyncMock()
    fake_kvs_client.get_record = AsyncMock(return_value=None)

    with patch.object(AliasResolver, '_get_default_kvs_client', return_value=fake_kvs_client):
        await AliasResolver._get_alias_map(config)
        await AliasResolver._get_alias_map(config)
        await AliasResolver._get_alias_map(config)

    assert fake_kvs_client.get_record.await_count == 1
    assert AliasResolver._alias_map == {}


async def test_store_mapping_uses_injected_configuration_is_at_home() -> None:
    """`store_mapping` gates on the injected configuration's `is_at_home`, not the global one."""
    # Global `is_at_home` defaults to False; injected config says True — the KVS write must still happen.
    config = Configuration(is_at_home=True, token='test-token', default_key_value_store_id='default-kvs-id')
    resolver = AliasResolver(storage_type='Dataset', alias='test-alias', configuration=config)

    fake_kvs_client = AsyncMock()
    fake_kvs_client.get_record = AsyncMock(return_value=None)
    fake_kvs_client.set_record = AsyncMock(return_value=None)
    fake_kvs_client.get = AsyncMock(return_value={'id': 'default-kvs-id'})

    with patch.object(AliasResolver, '_get_default_kvs_client', return_value=fake_kvs_client):
        await resolver.store_mapping(storage_id='new-id-789')

    fake_kvs_client.set_record.assert_awaited_once()
    assert AliasResolver._alias_map[resolver._storage_key] == 'new-id-789'


async def test_configuration_storages_alias_resolving() -> None:
    """Test that `AliasResolver` correctly resolves ids of storages registered in Configuration."""

    # Actor storages
    datasets = {'default': 'default_dataset_id', 'custom': 'custom_Dataset_id'}
    request_queues = {'default': 'default_request_queue_id', 'custom': 'custom_RequestQueue_id'}
    key_value_stores = {'default': 'default_key_value_store_id', 'custom': 'custom_KeyValueStore_id'}

    # Set up the configuration with the storage mapping
    configuration = Configuration(
        actor_storages={'datasets': datasets, 'request_queues': request_queues, 'key_value_stores': key_value_stores}
    )

    # Check that id of each non-default storage saved in the mapping is resolved
    for storage_type in ('Dataset', 'KeyValueStore', 'RequestQueue'):
        assert (
            await AliasResolver(storage_type=storage_type, alias='custom', configuration=configuration).resolve_id()
            == f'custom_{storage_type}_id'
        )
