import os

import pytest

from apify.memory_storage.memory_storage import MemoryStorage
from apify.memory_storage.resource_clients.dataset_collection import DatasetCollectionClient


@pytest.fixture()
def datasets_client(memory_storage: MemoryStorage) -> DatasetCollectionClient:
    return memory_storage.datasets()


async def test_get_or_create(datasets_client: DatasetCollectionClient) -> None:
    dataset_name = 'test'
    # A new dataset gets created
    assert os.path.exists(os.path.join(datasets_client.datasets_directory, dataset_name, '__metadata__.json')) is False
    dataset_info = await datasets_client.get_or_create(name=dataset_name)
    assert dataset_info['name'] == dataset_name
    assert os.path.exists(os.path.join(datasets_client.datasets_directory, dataset_name, '__metadata__.json')) is True
    # Another get_or_create call returns the same dataset
    dataset_info_existing = await datasets_client.get_or_create(name=dataset_name)
    assert dataset_info['id'] == dataset_info_existing['id']
    assert dataset_info['name'] == dataset_info_existing['name']
    assert dataset_info['createdAt'] == dataset_info_existing['createdAt']


async def test_list(datasets_client: DatasetCollectionClient) -> None:
    assert datasets_client.list().count == 0
    dataset_info = await datasets_client.get_or_create(name='dataset')
    dataset_list = datasets_client.list()
    assert dataset_list.count == 1
    assert dataset_list.items[0]['name'] == dataset_info['name']
    # Test sorting behavior
    newer_dataset_info = await datasets_client.get_or_create(name='newer-dataset')
    dataset_list_sorting = datasets_client.list()
    assert dataset_list_sorting.count == 2
    assert dataset_list_sorting.items[0]['name'] == dataset_info['name']
    assert dataset_list_sorting.items[1]['name'] == newer_dataset_info['name']
