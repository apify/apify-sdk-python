import os

import pytest

from apify.memory_storage.memory_storage import MemoryStorage
from apify.memory_storage.resource_clients.dataset import DatasetClient


@pytest.fixture()
async def dataset_client(memory_storage: MemoryStorage) -> DatasetClient:
    datasets_client = memory_storage.datasets()
    dataset_info = await datasets_client.get_or_create(name='test')
    return memory_storage.dataset(id=dataset_info['id'])


async def test_nonexistent(memory_storage: MemoryStorage) -> None:
    dataset_client = memory_storage.dataset(id='clearly not a uuid')
    assert await dataset_client.get() is None
    with pytest.raises(ValueError):
        await dataset_client.update(name='test-update')
        await dataset_client.list_items()
        await dataset_client.push_items([{'abc': 123}])
    await dataset_client.delete()


async def test_not_implemented(dataset_client: DatasetClient) -> None:
    with pytest.raises(NotImplementedError):
        await dataset_client.stream_items()
        await dataset_client.get_items_as_bytes()


async def test_get(dataset_client: DatasetClient) -> None:
    info = await dataset_client.get()
    assert info is not None
    assert info['id'] == dataset_client.id
    assert info['accessedAt'] != info['createdAt']


async def test_update(dataset_client: DatasetClient) -> None:
    new_dataset_name = 'test-update'
    old_dataset_info = await dataset_client.get()
    assert old_dataset_info is not None
    old_dataset_directory = os.path.join(dataset_client.client.datasets_directory, old_dataset_info['name'])
    new_dataset_directory = os.path.join(dataset_client.client.datasets_directory, new_dataset_name)
    assert os.path.exists(os.path.join(old_dataset_directory, '__metadata__.json')) is True
    assert os.path.exists(os.path.join(new_dataset_directory, '__metadata__.json')) is False
    updated_dataset_info = await dataset_client.update(name=new_dataset_name)
    assert os.path.exists(os.path.join(old_dataset_directory, '__metadata__.json')) is False
    assert os.path.exists(os.path.join(new_dataset_directory, '__metadata__.json')) is True
    # Only modifiedAt and accessedAt should be different
    assert old_dataset_info['createdAt'] == updated_dataset_info['createdAt']
    assert old_dataset_info['modifiedAt'] != updated_dataset_info['modifiedAt']
    assert old_dataset_info['accessedAt'] != updated_dataset_info['accessedAt']
    # Should fail with the same name
    with pytest.raises(ValueError):
        await dataset_client.update(name=new_dataset_name)


async def test_delete(dataset_client: DatasetClient) -> None:
    dataset_info = await dataset_client.get()
    assert dataset_info is not None
    dataset_directory = os.path.join(dataset_client.client.datasets_directory, dataset_info['name'])
    assert os.path.exists(os.path.join(dataset_directory, '__metadata__.json')) is True
    await dataset_client.delete()
    assert os.path.exists(os.path.join(dataset_directory, '__metadata__.json')) is False
    # Does not crash when called again
    await dataset_client.delete()


async def test_push_items(dataset_client: DatasetClient) -> None:
    await dataset_client.push_items('{"test": "JSON from a string"}')
    await dataset_client.push_items({'abc': {'def': {'ghi': '123'}}})
    await dataset_client.push_items(['{"test-json-parse": "JSON from a string"}' for _ in range(10)])
    await dataset_client.push_items([{'test-dict': i} for i in range(10)])
    list_page = await dataset_client.list_items()
    assert list_page.items[0]['test'] == 'JSON from a string'
    assert list_page.items[1]['abc']['def']['ghi'] == '123'
    assert list_page.items[11]['test-json-parse'] == 'JSON from a string'
    assert list_page.items[21]['test-dict'] == 9
    assert list_page.count == 22


async def test_list_items(dataset_client: DatasetClient) -> None:
    item_count = 100
    used_offset = 10
    used_limit = 50
    await dataset_client.push_items([{'id': i} for i in range(item_count)])
    # Test without any parameters
    list_default = await dataset_client.list_items()
    assert list_default.count == item_count
    assert list_default.offset == 0
    assert list_default.items[0]['id'] == 0
    assert list_default.desc is False
    # Test offset
    list_offset_10 = await dataset_client.list_items(offset=used_offset)
    assert list_offset_10.count == item_count - used_offset
    assert list_offset_10.offset == used_offset
    assert list_offset_10.total == item_count
    assert list_offset_10.items[0]['id'] == used_offset
    # Test limit
    list_limit_50 = await dataset_client.list_items(limit=used_limit)
    assert list_limit_50.count == used_limit
    assert list_limit_50.limit == used_limit
    assert list_limit_50.total == item_count
    # Test desc
    list_desc_true = await dataset_client.list_items(desc=True)
    assert list_desc_true.items[0]['id'] == 99
    assert list_desc_true.desc is True


async def test_iterate_items(dataset_client: DatasetClient) -> None:
    item_count = 100
    await dataset_client.push_items([{'id': i} for i in range(item_count)])
    actual_items = []
    async for item in dataset_client.iterate_items():
        assert 'id' in item.keys()
        actual_items.append(item)
    assert len(actual_items) == item_count
    assert actual_items[0]['id'] == 0
    assert actual_items[99]['id'] == 99
