import os

import pytest

from apify.memory_storage.memory_storage import MemoryStorage
from apify.memory_storage.resource_clients.key_value_store_collection import KeyValueStoreCollectionClient


@pytest.fixture()
def key_value_stores_client(tmp_path: str) -> KeyValueStoreCollectionClient:
    return MemoryStorage(local_data_directory=tmp_path, write_metadata=True).key_value_stores()


@pytest.mark.asyncio
async def test_get_or_create(key_value_stores_client: KeyValueStoreCollectionClient) -> None:
    kvs_name = 'test'
    # A new kvs gets created
    assert os.path.exists(os.path.join(key_value_stores_client.key_value_stores_directory, kvs_name, '__metadata__.json')) is False
    kvs_info = await key_value_stores_client.get_or_create(name=kvs_name)
    assert kvs_info['name'] == kvs_name
    assert os.path.exists(os.path.join(key_value_stores_client.key_value_stores_directory, kvs_name, '__metadata__.json')) is True
    # Another get_or_create call returns the same kvs
    kvs_info_existing = await key_value_stores_client.get_or_create(name=kvs_name)
    assert kvs_info['id'] == kvs_info_existing['id']
    assert kvs_info['name'] == kvs_info_existing['name']
    assert kvs_info['createdAt'] == kvs_info_existing['createdAt']


@pytest.mark.asyncio
async def test_list(key_value_stores_client: KeyValueStoreCollectionClient) -> None:
    assert key_value_stores_client.list().count == 0
    kvs_info = await key_value_stores_client.get_or_create(name='kvs')
    kvs_list = key_value_stores_client.list()
    assert kvs_list.count == 1
    assert kvs_list.items[0]['name'] == kvs_info['name']
    # Test sorting behavior
    newer_kvs_info = await key_value_stores_client.get_or_create(name='newer-kvs')
    kvs_list_sorting = key_value_stores_client.list()
    assert kvs_list_sorting.count == 2
    assert kvs_list_sorting.items[0]['name'] == kvs_info['name']
    assert kvs_list_sorting.items[1]['name'] == newer_kvs_info['name']
