from __future__ import annotations

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


async def test_alias_map_cached_locally() -> None:
    """Test that alias map is returned from memory when already loaded."""
    AliasResolver._alias_map = {'existing_key': 'existing_id'}
    config = Configuration(is_at_home=False, token='test-token')

    result = await AliasResolver._get_alias_map(config)
    assert result == {'existing_key': 'existing_id'}
