import os

import pytest

from apify.memory_storage.memory_storage import MemoryStorage
from apify.memory_storage.resource_clients.request_queue_collection import RequestQueueCollectionClient


@pytest.fixture()
def request_queues_client(memory_storage: MemoryStorage) -> RequestQueueCollectionClient:
    return memory_storage.request_queues()


async def test_get_or_create(request_queues_client: RequestQueueCollectionClient) -> None:
    rq_name = 'test'
    # A new request queue gets created
    assert os.path.exists(os.path.join(request_queues_client._request_queues_directory, rq_name, '__metadata__.json')) is False
    rq_info = await request_queues_client.get_or_create(name=rq_name)
    assert rq_info['name'] == rq_name
    assert os.path.exists(os.path.join(request_queues_client._request_queues_directory, rq_name, '__metadata__.json')) is True
    # Another get_or_create call returns the same request queue
    rq_existing = await request_queues_client.get_or_create(name=rq_name)
    assert rq_info['id'] == rq_existing['id']
    assert rq_info['name'] == rq_existing['name']
    assert rq_info['createdAt'] == rq_existing['createdAt']


async def test_list(request_queues_client: RequestQueueCollectionClient) -> None:
    assert request_queues_client.list().count == 0
    rq_info = await request_queues_client.get_or_create(name='dataset')
    rq_list = request_queues_client.list()
    assert rq_list.count == 1
    assert rq_list.items[0]['name'] == rq_info['name']
    # Test sorting behavior
    newer_rq_info = await request_queues_client.get_or_create(name='newer-dataset')
    rq_list_sorting = request_queues_client.list()
    assert rq_list_sorting.count == 2
    assert rq_list_sorting.items[0]['name'] == rq_info['name']
    assert rq_list_sorting.items[1]['name'] == newer_rq_info['name']
