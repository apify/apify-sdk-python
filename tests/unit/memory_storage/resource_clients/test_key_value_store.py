import os

import pytest

from apify.memory_storage import MemoryStorage
from apify.memory_storage.resource_clients import KeyValueStoreClient


@pytest.fixture()
async def key_value_store_client(memory_storage: MemoryStorage) -> KeyValueStoreClient:
    key_value_stores_client = memory_storage.key_value_stores()
    kvs_info = await key_value_stores_client.get_or_create(name='test')
    return memory_storage.key_value_store(kvs_info['id'])


async def test_nonexistent(memory_storage: MemoryStorage) -> None:
    kvs_client = memory_storage.key_value_store(key_value_store_id='clearly not a uuid')
    assert await kvs_client.get() is None
    with pytest.raises(ValueError):
        await kvs_client.update(name='test-update')
        await kvs_client.list_keys()
        await kvs_client.set_record('test', {'abc': 123})
        await kvs_client.get_record('test')
        await kvs_client.get_record_as_bytes('test')
        await kvs_client.delete_record('test')
    await kvs_client.delete()


async def test_not_implemented(key_value_store_client: KeyValueStoreClient) -> None:
    with pytest.raises(NotImplementedError):
        await key_value_store_client.stream_record('test')


async def test_get(key_value_store_client: KeyValueStoreClient) -> None:
    info = await key_value_store_client.get()
    assert info is not None
    assert info['id'] == key_value_store_client._id
    assert info['accessedAt'] != info['createdAt']


async def test_update(key_value_store_client: KeyValueStoreClient) -> None:
    new_kvs_name = 'test-update'
    old_kvs_info = await key_value_store_client.get()
    assert old_kvs_info is not None
    old_kvs_directory = os.path.join(key_value_store_client._client._key_value_stores_directory, old_kvs_info['name'])
    new_kvs_directory = os.path.join(key_value_store_client._client._key_value_stores_directory, new_kvs_name)
    assert os.path.exists(os.path.join(old_kvs_directory, '__metadata__.json')) is True
    assert os.path.exists(os.path.join(new_kvs_directory, '__metadata__.json')) is False
    updated_kvs_info = await key_value_store_client.update(name=new_kvs_name)
    assert os.path.exists(os.path.join(old_kvs_directory, '__metadata__.json')) is False
    assert os.path.exists(os.path.join(new_kvs_directory, '__metadata__.json')) is True
    # Only modifiedAt and accessedAt should be different
    assert old_kvs_info['createdAt'] == updated_kvs_info['createdAt']
    assert old_kvs_info['modifiedAt'] != updated_kvs_info['modifiedAt']
    assert old_kvs_info['accessedAt'] != updated_kvs_info['accessedAt']
    # Should fail with the same name
    with pytest.raises(ValueError):
        await key_value_store_client.update(name=new_kvs_name)


async def test_delete(key_value_store_client: KeyValueStoreClient) -> None:
    kvs_info = await key_value_store_client.get()
    assert kvs_info is not None
    kvs_directory = os.path.join(key_value_store_client._client._key_value_stores_directory, kvs_info['name'])
    assert os.path.exists(os.path.join(kvs_directory, '__metadata__.json')) is True
    await key_value_store_client.delete()
    assert os.path.exists(os.path.join(kvs_directory, '__metadata__.json')) is False
    # Does not crash when called again
    await key_value_store_client.delete()


async def test_list_keys(key_value_store_client: KeyValueStoreClient) -> None:
    record_count = 4
    used_limit = 2
    used_exclusive_start_key = 'a'
    await key_value_store_client.set_record('b', 'test')
    await key_value_store_client.set_record('a', 'test')
    await key_value_store_client.set_record('d', 'test')
    await key_value_store_client.set_record('c', 'test')
    # Default settings
    keys = await key_value_store_client.list_keys()
    assert keys['items'][0]['key'] == 'a'
    assert keys['items'][3]['key'] == 'd'
    assert keys['count'] == record_count
    assert keys['isTruncated'] is False
    # Test limit
    keys_limit_2 = await key_value_store_client.list_keys(limit=used_limit)
    assert keys_limit_2['count'] == record_count
    assert keys_limit_2['limit'] == used_limit
    assert keys_limit_2['items'][1]['key'] == 'b'
    # Test exclusive start key
    keys_exclusive_start = await key_value_store_client.list_keys(exclusive_start_key=used_exclusive_start_key, limit=2)
    assert keys_exclusive_start['exclusiveStartKey'] == used_exclusive_start_key
    assert keys_exclusive_start['isTruncated'] is True
    assert keys_exclusive_start['nextExclusiveStartKey'] == 'c'
    assert keys_exclusive_start['items'][0]['key'] == 'b'
    assert keys_exclusive_start['items'][-1]['key'] == keys_exclusive_start['nextExclusiveStartKey']


async def test_get_and_set_record(tmp_path: str, key_value_store_client: KeyValueStoreClient) -> None:
    # Test setting dict record
    dict_record_key = 'test-dict'
    await key_value_store_client.set_record(dict_record_key, {'test': 123})
    dict_record_info = await key_value_store_client.get_record(dict_record_key)
    assert dict_record_info is not None
    assert 'application/json' in dict_record_info['contentType']
    assert dict_record_info['value']['test'] == 123
    # Test setting str record
    str_record_key = 'test-str'
    await key_value_store_client.set_record(str_record_key, 'test')
    str_record_info = await key_value_store_client.get_record(str_record_key)
    assert str_record_info is not None
    assert 'text/plain' in str_record_info['contentType']
    assert str_record_info['value'] == 'test'
    # Test setting explicit json record but use str as value, i.e. json dumps is skipped
    explicit_json_key = 'test-json'
    await key_value_store_client.set_record(explicit_json_key, '{"test": "explicit string"}', 'application/json')
    bytes_record_info = await key_value_store_client.get_record(explicit_json_key)
    assert bytes_record_info is not None
    assert 'application/json' in bytes_record_info['contentType']
    assert bytes_record_info['value']['test'] == 'explicit string'
    # Test using bytes
    bytes_key = 'test-json'
    bytes_value = 'testing bytes set_record'.encode('utf-8')
    await key_value_store_client.set_record(bytes_key, bytes_value, 'unknown')
    bytes_record_info = await key_value_store_client.get_record(bytes_key)
    assert bytes_record_info is not None
    assert 'unknown' in bytes_record_info['contentType']
    assert bytes_record_info['value'] == bytes_value
    assert bytes_record_info['value'].decode('utf-8') == bytes_value.decode('utf-8')
    # Test using file descriptor
    with pytest.raises(NotImplementedError):
        with open(os.path.join(tmp_path, 'test.json'), 'w+') as f:
            f.write('Test')
            await key_value_store_client.set_record('file', f)


async def test_get_record_as_bytes(key_value_store_client: KeyValueStoreClient) -> None:
    record_key = 'test'
    record_value = 'testing'
    await key_value_store_client.set_record(record_key, record_value)
    record_info = await key_value_store_client.get_record_as_bytes(record_key)
    assert record_info is not None
    assert record_info['value'] == record_value.encode('utf-8')


async def test_delete_record(key_value_store_client: KeyValueStoreClient) -> None:
    record_key = 'test'
    await key_value_store_client.set_record(record_key, 'test')
    await key_value_store_client.delete_record(record_key)
    # Does not crash when called again
    await key_value_store_client.delete_record(record_key)
