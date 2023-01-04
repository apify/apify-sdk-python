import os
from datetime import datetime

import pytest

from apify.memory_storage.memory_storage import MemoryStorage
from apify.memory_storage.resource_clients.request_queue import RequestQueueClient


@pytest.fixture()
async def request_queue_client(memory_storage: MemoryStorage) -> RequestQueueClient:
    request_queues_client = memory_storage.request_queues()
    rq_info = await request_queues_client.get_or_create(name='test')
    return memory_storage.request_queue(rq_info['id'])


async def test_nonexistent(memory_storage: MemoryStorage) -> None:
    request_queue_client = memory_storage.request_queue(request_queue_id='clearly not a uuid')
    assert await request_queue_client.get() is None
    with pytest.raises(ValueError):
        await request_queue_client.update(name='test-update')
    await request_queue_client.delete()


async def test_get(request_queue_client: RequestQueueClient) -> None:
    info = await request_queue_client.get()
    assert info is not None
    assert info['id'] == request_queue_client._id
    assert info['accessedAt'] != info['createdAt']


async def test_update(request_queue_client: RequestQueueClient) -> None:
    new_rq_name = 'test-update'
    old_rq_info = await request_queue_client.get()
    assert old_rq_info is not None
    old_rq_directory = os.path.join(request_queue_client._client._request_queues_directory, old_rq_info['name'])
    new_rq_directory = os.path.join(request_queue_client._client._request_queues_directory, new_rq_name)
    assert os.path.exists(os.path.join(old_rq_directory, '__metadata__.json')) is True
    assert os.path.exists(os.path.join(new_rq_directory, '__metadata__.json')) is False
    updated_rq_info = await request_queue_client.update(name=new_rq_name)
    assert os.path.exists(os.path.join(old_rq_directory, '__metadata__.json')) is False
    assert os.path.exists(os.path.join(new_rq_directory, '__metadata__.json')) is True
    # Only modifiedAt and accessedAt should be different
    assert old_rq_info['createdAt'] == updated_rq_info['createdAt']
    assert old_rq_info['modifiedAt'] != updated_rq_info['modifiedAt']
    assert old_rq_info['accessedAt'] != updated_rq_info['accessedAt']
    # Should fail with the same name
    with pytest.raises(ValueError):
        await request_queue_client.update(name=new_rq_name)


async def test_delete(request_queue_client: RequestQueueClient) -> None:
    rq_info = await request_queue_client.get()
    assert rq_info is not None
    rq_directory = os.path.join(request_queue_client._client._request_queues_directory, rq_info['name'])
    assert os.path.exists(os.path.join(rq_directory, '__metadata__.json')) is True
    await request_queue_client.delete()
    assert os.path.exists(os.path.join(rq_directory, '__metadata__.json')) is False
    # Does not crash when called again
    await request_queue_client.delete()


async def test_list_head(request_queue_client: RequestQueueClient) -> None:
    request_1_url = 'https://apify.com'
    request_2_url = 'https://example.com'
    await request_queue_client.add_request({
        'uniqueKey': request_1_url,
        'url': request_1_url,
    })
    await request_queue_client.add_request({
        'uniqueKey': request_2_url,
        'url': request_2_url,
    })
    list_head = await request_queue_client.list_head()
    assert len(list_head['items']) == 2
    for item in list_head['items']:
        assert 'id' in item.keys()


async def test_add_record(request_queue_client: RequestQueueClient) -> None:
    # TODO: How can we test the forefront parameter?
    request_forefront_url = 'https://apify.com'
    request_not_forefront_url = 'https://example.com'
    request_forefront_info = await request_queue_client.add_request({
        'uniqueKey': request_forefront_url,
        'url': request_forefront_url,
    }, forefront=True)
    request_not_forefront_info = await request_queue_client.add_request({
        'uniqueKey': request_not_forefront_url,
        'url': request_not_forefront_url,
    }, forefront=False)
    assert request_forefront_info.get('requestId') is not None
    assert request_not_forefront_info.get('requestId') is not None
    assert request_forefront_info['wasAlreadyHandled'] is False
    assert request_not_forefront_info['wasAlreadyHandled'] is False
    rq_info = await request_queue_client.get()
    assert rq_info is not None
    assert rq_info['pendingRequestCount'] == rq_info['totalRequestCount'] == 2


async def test_get_record(request_queue_client: RequestQueueClient) -> None:
    request_url = 'https://apify.com'
    request_info = await request_queue_client.add_request({
        'uniqueKey': request_url,
        'url': request_url,
    })
    request = await request_queue_client.get_request(request_info['requestId'])
    assert request is not None
    assert 'id' in request.keys()
    assert request['url'] == request['uniqueKey'] == request_url
    # Non-existent id
    assert (await request_queue_client.get_request('non-existent id')) is None


async def test_update_record(request_queue_client: RequestQueueClient) -> None:
    # TODO: How can we test the forefront parameter?
    request_url = 'https://apify.com'
    request_info = await request_queue_client.add_request({
        'uniqueKey': request_url,
        'url': request_url,
    })
    request = await request_queue_client.get_request(request_info['requestId'])
    assert request is not None
    rq_info_before_update = await request_queue_client.get()
    assert rq_info_before_update is not None
    assert rq_info_before_update['pendingRequestCount'] == 1
    request_update_info = await request_queue_client.update_request({**request, 'handledAt': datetime.utcnow()})
    assert request_update_info['wasAlreadyHandled'] is False
    rq_info_after_update = await request_queue_client.get()
    assert rq_info_after_update is not None
    assert rq_info_after_update['pendingRequestCount'] == 0


async def test_delete_record(request_queue_client: RequestQueueClient) -> None:
    request_url = 'https://apify.com'
    request_info = await request_queue_client.add_request({
        'uniqueKey': request_url,
        'url': request_url,
    })
    rq_info_before_update = await request_queue_client.get()
    assert rq_info_before_update is not None
    assert rq_info_before_update['pendingRequestCount'] == 1
    await request_queue_client.delete_request(request_info['requestId'])
    rq_info_after_update = await request_queue_client.get()
    assert rq_info_after_update is not None
    assert rq_info_after_update['pendingRequestCount'] == 0
    # Does not crash when called again
    await request_queue_client.delete_request(request_info['requestId'])
