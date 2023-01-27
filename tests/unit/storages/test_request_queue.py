import asyncio

import pytest

from apify.storages import RequestQueue


@pytest.fixture()
async def request_queue() -> RequestQueue:
    return await RequestQueue.open()


async def test_same_references() -> None:
    rq1 = await RequestQueue.open()
    rq2 = await RequestQueue.open()
    assert rq1 is rq2
    rq_name = 'non-default'
    rq_named1 = await RequestQueue.open(rq_name)
    rq_named2 = await RequestQueue.open(rq_name)
    assert rq_named1 is rq_named2


async def test_drop() -> None:
    rq1 = await RequestQueue.open()
    await rq1.drop()
    rq2 = await RequestQueue.open()
    assert rq1 is not rq2


async def test_add_fetch_handle_request(request_queue: RequestQueue) -> None:
    url = 'https://example.com'
    assert await request_queue.is_empty() is True
    add_request_info = await request_queue.add_request({
        'uniqueKey': url,
        'url': url,
    })
    assert add_request_info['wasAlreadyPresent'] is False
    assert add_request_info['wasAlreadyHandled'] is False
    assert await request_queue.is_empty() is False
    # Fetch the request
    next = await request_queue.fetch_next_request()
    assert next is not None
    # Mark it as handled
    queue_operation_info = await request_queue.mark_request_as_handled(next)
    assert queue_operation_info is not None
    assert queue_operation_info['uniqueKey'] == url
    assert await request_queue.is_finished() is True


async def test_reclaim_request(request_queue: RequestQueue) -> None:
    url = 'https://example.com'
    await request_queue.add_request({
        'uniqueKey': url,
        'url': url,
    })
    # Fetch the request
    next = await request_queue.fetch_next_request()
    assert next is not None
    assert next['uniqueKey'] == url
    # Reclaim
    await request_queue.reclaim_request(next)
    # Try to fetch again after a few secs
    await asyncio.sleep(4)  # 3 seconds is the consistency delay in request queue
    next_again = await request_queue.fetch_next_request()
    assert next_again is not None
    assert next_again['uniqueKey'] == url
