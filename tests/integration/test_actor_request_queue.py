from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest

from apify_shared.consts import ApifyEnvVars

from ._utils import generate_unique_resource_name
from apify import Actor, Request

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from apify_client import ApifyClientAsync
    from crawlee.storages import RequestQueue

    from .conftest import MakeActorFunction, RunActorFunction


@pytest.fixture
async def apify_named_rq(
    apify_client_async: ApifyClientAsync, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[RequestQueue]:
    assert apify_client_async.token
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_client_async.token)
    request_queue_name = generate_unique_resource_name('request_queue')

    async with Actor:
        request_queue = await Actor.open_request_queue(name=request_queue_name, force_cloud=True)
        yield request_queue
        await request_queue.drop()


async def test_same_references_in_default_rq(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        async with Actor:
            rq1 = await Actor.open_request_queue()
            rq2 = await Actor.open_request_queue()
            assert rq1 is rq2

    actor = await make_actor(label='rq-same-ref-default', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_same_references_in_named_rq(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    rq_name = generate_unique_resource_name('request-queue')

    async def main() -> None:
        async with Actor:
            input_object = await Actor.get_input()
            rq_name = input_object['rqName']
            rq_by_name_1 = await Actor.open_request_queue(name=rq_name)
            rq_by_name_2 = await Actor.open_request_queue(name=rq_name)
            assert rq_by_name_1 is rq_by_name_2

            rq_1_metadata = await rq_by_name_1.get_metadata()
            rq_by_id_1 = await Actor.open_request_queue(id=rq_1_metadata.id)
            rq_by_id_2 = await Actor.open_request_queue(id=rq_1_metadata.id)
            assert rq_by_id_1 is rq_by_name_1
            assert rq_by_id_2 is rq_by_id_1

            await rq_by_name_1.drop()

    actor = await make_actor(label='rq-same-ref-named', main_func=main)
    run_result = await run_actor(actor, run_input={'rqName': rq_name})

    assert run_result.status == 'SUCCEEDED'


async def test_force_cloud(
    apify_client_async: ApifyClientAsync,
    apify_named_rq: RequestQueue,
) -> None:
    request_queue_id = (await apify_named_rq.get_metadata()).id
    request_info = await apify_named_rq.add_request(Request.from_url('http://example.com'))
    assert request_info.id is not None
    request_queue_client = apify_client_async.request_queue(request_queue_id)

    request_queue_details = await request_queue_client.get()
    assert request_queue_details is not None
    assert request_queue_details.get('name') == apify_named_rq.name

    request_queue_request = await request_queue_client.get_request(request_info.id)
    assert request_queue_request is not None
    assert request_queue_request['url'] == 'http://example.com'


async def test_request_queue_is_finished(
    apify_named_rq: RequestQueue,
) -> None:
    request_queue = await Actor.open_request_queue(name=apify_named_rq.name, force_cloud=True)
    await request_queue.add_request(Request.from_url('http://example.com'))
    assert not await request_queue.is_finished()

    request = await request_queue.fetch_next_request()
    assert request is not None
    assert not await request_queue.is_finished(), (
        'RequestQueue should not be finished unless the request is marked as handled.'
    )

    await request_queue.mark_request_as_handled(request)
    assert await request_queue.is_finished()


async def test_request_queue_deduplication(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test that the deduplication works correctly. Try to add 2 similar requests, but it should call API just once.

    Deduplication works based on the request's `unique_key` only. To include more attributes in the unique key the
    `use_extended_unique_key=True` argument of `Request.from_url` method can be used.
    This tests internal optimization that changes no behavior for the user.
    The functions input/output behave the same way,it only uses less amount of API calls.
    """

    async def main() -> None:
        import asyncio

        from apify import Actor, Request

        async with Actor:
            request1 = Request.from_url('http://example.com', method='POST')
            request2 = Request.from_url('http://example.com', method='GET')
            rq = await Actor.open_request_queue()

            await asyncio.sleep(10)  # Wait to be sure that metadata are updated

            # Get raw client, because stats are not exposed in `RequestQueue` class, but are available in raw client
            rq_client = Actor.apify_client.request_queue(request_queue_id=rq.id)
            _rq = await rq_client.get()
            assert _rq
            stats_before = _rq.get('stats', {})
            Actor.log.info(stats_before)

            # Add same request twice
            await rq.add_request(request1)
            await rq.add_request(request2)

            await asyncio.sleep(10)  # Wait to be sure that metadata are updated
            _rq = await rq_client.get()
            assert _rq
            stats_after = _rq.get('stats', {})
            Actor.log.info(stats_after)

            assert (stats_after['writeCount'] - stats_before['writeCount']) == 1

    actor = await make_actor(label='rq-deduplication', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_request_queue_deduplication_use_extended_unique_key(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test that the deduplication works correctly. Try to add 2 similar requests and it should call API just twice.

    Deduplication works based on the request's `unique_key` only. To include more attributes in the unique key the
    `use_extended_unique_key=True` argument of `Request.from_url` method can be used.
    This tests internal optimization that changes no behavior for the user.
    The functions input/output behave the same way,it only uses less amount of API calls.
    """

    async def main() -> None:
        import asyncio

        from apify import Actor, Request

        async with Actor:
            request1 = Request.from_url('http://example.com', method='POST', use_extended_unique_key=True)
            request2 = Request.from_url('http://example.com', method='GET', use_extended_unique_key=True)
            rq = await Actor.open_request_queue()

            await asyncio.sleep(10)  # Wait to be sure that metadata are updated

            # Get raw client, because stats are not exposed in `RequestQueue` class, but are available in raw client
            rq_client = Actor.apify_client.request_queue(request_queue_id=rq.id)
            _rq = await rq_client.get()
            assert _rq
            stats_before = _rq.get('stats', {})
            Actor.log.info(stats_before)

            # Add same request twice
            await rq.add_request(request1)
            await rq.add_request(request2)

            await asyncio.sleep(10)  # Wait to be sure that metadata are updated
            _rq = await rq_client.get()
            assert _rq
            stats_after = _rq.get('stats', {})
            Actor.log.info(stats_after)

            assert (stats_after['writeCount'] - stats_before['writeCount']) == 2

    actor = await make_actor(label='rq-deduplication', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_request_queue_parallel_deduplication(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test that the deduplication works correctly even with parallel attempts to add same links.

    The test is set up in a way for workers to have some requests that were already added to the queue and some new
    requests. The function must correctly deduplicate the requests and add only new requests. For example:
    First worker adding 10 new requests,
    second worker adding 10 new requests and 10 known requests,
    third worker adding 10 new requests and 20 known requests and so on"""

    async def main() -> None:
        import asyncio
        import logging

        from apify import Actor, Request

        worker_count = 10
        max_requests = 100
        batch_size = iter(range(10, max_requests + 1, int(max_requests / worker_count)))

        async with Actor:
            logging.getLogger('apify.storage_clients._apify._request_queue_client').setLevel(logging.DEBUG)

            requests = [Request.from_url(f'http://example.com/{i}') for i in range(max_requests)]
            rq = await Actor.open_request_queue()

            await asyncio.sleep(10)  # Wait to be sure that metadata are updated

            # Get raw client, because stats are not exposed in `RequestQueue` class, but are available in raw client
            rq_client = Actor.apify_client.request_queue(request_queue_id=rq.id)
            _rq = await rq_client.get()
            assert _rq
            stats_before = _rq.get('stats', {})
            Actor.log.info(stats_before)

            # Add batches of some new and some already present requests in workers
            async def add_requests_worker() -> None:
                await rq.add_requests(requests[: next(batch_size)])

            # Start all workers
            add_requests_workers = [asyncio.create_task(add_requests_worker()) for _ in range(worker_count)]
            await asyncio.gather(*add_requests_workers)

            await asyncio.sleep(10)  # Wait to be sure that metadata are updated
            _rq = await rq_client.get()
            assert _rq
            stats_after = _rq.get('stats', {})
            Actor.log.info(stats_after)

            assert (stats_after['writeCount'] - stats_before['writeCount']) == len(requests)

    actor = await make_actor(label='rq-parallel-deduplication', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_request_queue_deduplication_unprocessed_requests(
    apify_named_rq: RequestQueue,
) -> None:
    """Test that the deduplication does not add unprocessed requests to the cache.

    In this test the first call is "hardcoded" to fail, even on all retries, so it never even sends the API request and
    thus has no chance of increasing the `writeCount`. The second call can increase the `writeCount` only if it is not
    cached, as cached requests do not make the call (tested in other tests). So this means the `unprocessedRequests`
    request was intentionally not cached."""
    logging.getLogger('apify.storage_clients._apify._request_queue_client').setLevel(logging.DEBUG)

    await asyncio.sleep(10)  # Wait to be sure that metadata are updated

    # Get raw client, because stats are not exposed in `RequestQueue` class, but are available in raw client
    rq_client = Actor.apify_client.request_queue(request_queue_id=apify_named_rq.id)
    _rq = await rq_client.get()
    assert _rq
    stats_before = _rq.get('stats', {})
    Actor.log.info(stats_before)

    def return_unprocessed_requests(requests: list[dict], *_: Any, **__: Any) -> dict[str, list[dict]]:
        """Simulate API returning unprocessed requests."""
        return {
            'processedRequests': [],
            'unprocessedRequests': [
                {'url': request['url'], 'uniqueKey': request['uniqueKey'], 'method': request['method']}
                for request in requests
            ],
        }

    with mock.patch(
        'apify_client.clients.resource_clients.request_queue.RequestQueueClientAsync.batch_add_requests',
        side_effect=return_unprocessed_requests,
    ):
        # Simulate failed API call for adding requests. Request was not processed and should not be cached.
        await apify_named_rq.add_requests(['http://example.com/1'])

    # This will succeed.
    await apify_named_rq.add_requests(['http://example.com/1'])

    await asyncio.sleep(10)  # Wait to be sure that metadata are updated
    _rq = await rq_client.get()
    assert _rq
    stats_after = _rq.get('stats', {})
    Actor.log.info(stats_after)

    assert (stats_after['writeCount'] - stats_before['writeCount']) == 1
