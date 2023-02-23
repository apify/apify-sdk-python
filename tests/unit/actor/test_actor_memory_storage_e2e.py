from pathlib import Path

import pytest

from apify import Actor
from apify.config import Configuration
from apify.consts import ApifyEnvVars
from apify.memory_storage import MemoryStorage
from apify.storages import Dataset, KeyValueStore, RequestQueue, StorageClientManager


@pytest.mark.parametrize('purge_on_start', [True, False])
async def test_actor_memory_storage_e2e(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, purge_on_start: bool) -> None:
    """This test simulates two clean runs using memory storage.
    The second run attempts to access data created by the first one.
    We run 2 configurations with different `purge_on_start`."""
    # Configure purging env var
    monkeypatch.setenv(ApifyEnvVars.PURGE_ON_START, 'true' if purge_on_start else 'false')
    # Store old storage client so we have the object reference for comparison
    old_client = StorageClientManager.get_storage_client()
    async with Actor:
        old_default_kvs = await Actor.open_key_value_store()
        old_non_default_kvs = await Actor.open_key_value_store(name='non-default')
        # Create data in default and non-default key-value store
        await old_default_kvs.set_value('test', 'default value')
        await old_non_default_kvs.set_value('test', 'non-default value')

    # Clean up singletons and mock a new memory storage
    monkeypatch.setattr(Actor, '_default_instance', None)
    monkeypatch.setattr(Configuration, '_default_instance', None)
    monkeypatch.setattr(Dataset, '_cache_by_id', None)
    monkeypatch.setattr(Dataset, '_cache_by_name', None)
    monkeypatch.setattr(KeyValueStore, '_cache_by_id', None)
    monkeypatch.setattr(KeyValueStore, '_cache_by_name', None)
    monkeypatch.setattr(RequestQueue, '_cache_by_id', None)
    monkeypatch.setattr(RequestQueue, '_cache_by_name', None)
    monkeypatch.setattr(StorageClientManager, '_default_instance', None)

    new_patched_memory_storage = MemoryStorage(local_data_directory=str(tmp_path))

    def get_storage_client(force_cloud: bool = False) -> 'MemoryStorage':  # noqa: U100
        return new_patched_memory_storage
    monkeypatch.setattr(StorageClientManager, 'get_storage_client', get_storage_client)

    # We simulate another clean run, we expect the memory storage to read from the local data directory
    # Default storages are purged based on purge_on_start parameter.
    async with Actor:
        # Check if we're using a different memory storage instance
        assert old_client is not StorageClientManager.get_storage_client()
        default_kvs = await Actor.open_key_value_store()
        assert default_kvs is not old_default_kvs
        non_default_kvs = await Actor.open_key_value_store(name='non-default')
        assert non_default_kvs is not old_non_default_kvs
        default_value = await default_kvs.get_value('test')
        non_default_value = await non_default_kvs.get_value('test')
        if purge_on_start:
            assert default_value is None
        else:
            assert default_value == 'default value'
        assert non_default_value == 'non-default value'
