from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest

from apify_shared.consts import ApifyEnvVars

from ._utils import generate_unique_resource_name
from apify import Actor, Request
from apify._models import ActorRun
from apify.storage_clients import ApifyStorageClient
from apify.storages import RequestQueue

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from apify_client import ApifyClientAsync

    from .conftest import MakeActorFunction, RunActorFunction


@pytest.fixture(params=['single', 'shared'])
async def apify_named_rq(
    apify_client_async: ApifyClientAsync, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> AsyncGenerator[RequestQueue]:
    assert apify_client_async.token
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_client_async.token)
    request_queue_name = generate_unique_resource_name('request_queue')

    async with Actor:
        request_queue = await RequestQueue.open(
            name=request_queue_name, storage_client=ApifyStorageClient(request_queue_access=request.param)
        )
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
    await apify_named_rq.add_request(Request.from_url('http://example.com'))
    assert not await apify_named_rq.is_finished()

    request = await apify_named_rq.fetch_next_request()
    assert request is not None
    assert not await apify_named_rq.is_finished(), (
        'RequestQueue should not be finished unless the request is marked as handled.'
    )

    await apify_named_rq.mark_request_as_handled(request)
    assert await apify_named_rq.is_finished()


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


async def test_request_queue_had_multiple_clients_platform(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test that `RequestQueue` clients created with different `client_key` appear as distinct clients."""

    async def main() -> None:
        from apify_client import ApifyClientAsync

        async with Actor:
            rq_1 = await Actor.open_request_queue()
            await rq_1.fetch_next_request()

            # Accessed with client created explicitly with `client_key=None` should appear as distinct client
            api_client = ApifyClientAsync(token=Actor.configuration.token).request_queue(
                request_queue_id=rq_1.id, client_key=None
            )
            await api_client.list_head()

            assert (await rq_1.get_metadata()).had_multiple_clients is True

    actor = await make_actor(label='rq-had-multiple-clients', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_request_queue_not_had_multiple_clients_platform(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test that same `RequestQueue` created from Actor does not act as multiple clients."""

    async def main() -> None:
        async with Actor:
            rq_1 = await Actor.open_request_queue()
            # Two calls to API to create situation where unset `client_key` can cause `had_multiple_clients` to True
            await rq_1.fetch_next_request()
            await rq_1.fetch_next_request()

            assert (await rq_1.get_metadata()).had_multiple_clients is False

    actor = await make_actor(label='rq-not-had-multiple-clients', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_request_queue_not_had_multiple_clients_platform_resurrection(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
    apify_client_async: ApifyClientAsync,
) -> None:
    """Test `RequestQueue` created from Actor does not act as multiple clients even after resurrection."""

    async def main() -> None:
        async with Actor:
            rq_1 = await Actor.open_request_queue()
            assert (await rq_1.get_metadata()).had_multiple_clients is False, 'Not accessed yet, should be False'

            await rq_1.fetch_next_request()

            assert (await rq_1.get_metadata()).had_multiple_clients is False, (
                'Accessed with the same client, should be False'
            )

    actor = await make_actor(label='rq-clients-resurrection', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'

    # Resurrect the run, the RequestQueue should still use same client key and thus not have multiple clients.
    run_client = apify_client_async.run(run_id=run_result.id)
    # Redirect logs even from the resurrected run
    streamed_log = await run_client.get_streamed_log(from_start=False)
    await run_client.resurrect()
    async with streamed_log:
        run_result = ActorRun.model_validate(await run_client.wait_for_finish(wait_secs=600))
        assert run_result.status == 'SUCCEEDED'


async def test_rq_defaults(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        from apify import Request
        from apify.storages import RequestQueue

        async with Actor:
            was_rebooted = await Actor.get_value('was_rebooted', default_value=False)

            rq_1 = await Actor.open_request_queue()
            rq_2 = await RequestQueue.open()

            assert rq_1 is rq_2

            if not was_rebooted:
                await rq_1.add_request(Request(url='https://example.com/rq_1', unique_key='rq_1'))
                await rq_2.add_request(Request(url='https://example.com/rq_2', unique_key='rq_2'))
                await Actor.set_value('was_rebooted', value=True)
                await Actor.reboot()

            rq_11 = await Actor.open_request_queue()
            rq_22 = await RequestQueue.open()

            assert rq_11 is rq_22
            assert rq_1.id == rq_11.id == rq_2.id == rq_22.id

            request_1 = await rq_11.fetch_next_request()
            request_2 = await rq_22.fetch_next_request()

            assert request_1 is not None
            assert request_2 is not None
            assert {request_1.url, request_2.url} == {'https://example.com/rq_1', 'https://example.com/rq_2'}

    actor = await make_actor(label='rq-defaults', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_rq_aliases(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        from apify import Request
        from apify.storages import RequestQueue

        async with Actor:
            was_rebooted = await Actor.get_value('was_rebooted', default_value=False)

            rq_1 = await Actor.open_request_queue(alias='my-alias-rq-1')
            rq_2 = await RequestQueue.open(alias='my-alias-rq-2')

            assert rq_1 is not rq_2
            assert rq_1.id != rq_2.id
            assert rq_1.name is None
            assert rq_2.name is None

            if not was_rebooted:
                await rq_1.add_request(Request(url='https://example.com/rq_1', unique_key='rq_1'))
                await rq_2.add_request(Request(url='https://example.com/rq_2', unique_key='rq_2'))
                await Actor.set_value('was_rebooted', value=True)
                await Actor.reboot()

            rq_11 = await Actor.open_request_queue(alias='my-alias-rq-1')
            rq_22 = await RequestQueue.open(alias='my-alias-rq-2')

            assert rq_1.id == rq_11.id
            assert rq_11 is rq_1

            assert rq_2.id == rq_22.id
            assert rq_22 is rq_2

            request_1 = await rq_11.fetch_next_request()
            request_2 = await rq_22.fetch_next_request()
            assert request_1 is not None
            assert request_1.url == 'https://example.com/rq_1'
            assert request_2 is not None
            assert request_2.url == 'https://example.com/rq_2'

    actor = await make_actor(label='rq-aliases', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'
