from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from .._utils import generate_unique_resource_name
from apify import Actor
from apify._models import ActorRun

if TYPE_CHECKING:
    from apify_client import ApifyClientAsync

    from .conftest import MakeActorFunction, RunActorFunction


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
        from crawlee import Request

        from apify import Actor

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
        from crawlee import Request

        from apify import Actor

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
        import logging

        from crawlee import Request

        from apify import Actor

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
        from crawlee import Request

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
        from crawlee import Request

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


@pytest.mark.skip(
    reason='The Apify RQ client is not resilient to concurrent processing, making this test flaky. See issue #529.'
)
async def test_concurrent_processing_simulation(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test simulation of concurrent request processing."""

    async def main() -> None:
        async with Actor:
            rq = await Actor.open_request_queue()
            Actor.log.info('Request queue opened')

            # Add requests for concurrent processing
            for i in range(20):
                await rq.add_request(f'https://example.com/concurrent/{i}')
            Actor.log.info('Added 20 requests for concurrent processing')

            total_count = await rq.get_total_count()
            assert total_count == 20, f'total_count={total_count}'

            # Simulate concurrent workers
            async def worker() -> int:
                processed = 0

                while request := await rq.fetch_next_request():
                    # Simulate some work
                    await asyncio.sleep(0.01)

                    # Randomly reclaim some requests (simulate failures)
                    if processed % 7 == 0 and processed > 0:  # Reclaim every 7th request
                        await rq.reclaim_request(request)
                    else:
                        await rq.mark_request_as_handled(request)
                        processed += 1

                return processed

            # Run multiple workers concurrently
            workers = [worker() for _ in range(3)]
            results = await asyncio.gather(*workers)

            total_processed = sum(results)
            Actor.log.info(f'Total processed by workers: {total_processed}')
            Actor.log.info(f'Individual worker results: {results}')

            # Verify that workers processed some requests
            assert total_processed > 0, f'total_processed={total_processed}'
            assert len(results) == 3, f'len(results)={len(results)}'

            # Check queue state after concurrent processing
            handled_after_workers = await rq.get_handled_count()
            assert handled_after_workers == total_processed, (
                f'handled_after_workers={handled_after_workers}',
                f'total_processed={total_processed}',
            )

            total_after_workers = await rq.get_total_count()
            assert total_after_workers == 20, f'total_after_workers={total_after_workers}'

            # Process any remaining reclaimed requests
            remaining_count = 0
            while not await rq.is_finished():
                request = await rq.fetch_next_request()
                if request:
                    remaining_count += 1
                    await rq.mark_request_as_handled(request)
                else:
                    break

            Actor.log.info(f'Processed {remaining_count} remaining requests')

            # Verify final state
            final_handled = await rq.get_handled_count()
            final_total = await rq.get_total_count()
            assert final_handled == 20, f'final_handled={final_handled}'
            assert final_total == 20, f'final_total={final_total}'
            assert total_processed + remaining_count == 20, (
                f'total_processed={total_processed}',
                f'remaining_count={remaining_count}',
            )

            is_finished = await rq.is_finished()
            assert is_finished is True, f'is_finished={is_finished}'

    actor = await make_actor(label='rq-concurrent-test', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'


async def test_rq_isolation(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test that different request queues are properly isolated."""

    async def main() -> None:
        async with Actor:
            # Get the unique actor name for creating unique queue names
            actor_name = Actor.configuration.actor_id

            # Open multiple queues with unique names
            rq1 = await Actor.open_request_queue(name=f'{actor_name}-rq-1')
            rq2 = await Actor.open_request_queue(name=f'{actor_name}-rq-2')
            Actor.log.info('Opened two separate named queues with unique names')

            # Verify they are different instances
            assert rq1 is not rq2, f'rq1 is rq2={rq1 is rq2}'
            Actor.log.info('Verified queues are different instances')

            # Add different requests to each queue
            await rq1.add_request('https://example.com/queue1-request')
            await rq2.add_request('https://example.com/queue2-request')
            Actor.log.info('Added different requests to each queue')

            # Verify isolation
            req1 = await rq1.fetch_next_request()
            req2 = await rq2.fetch_next_request()

            assert req1 is not None, f'req1={req1}'
            assert 'queue1' in req1.url, f'req1.url={req1.url}'
            assert req2 is not None, f'req2={req2}'
            assert 'queue2' in req2.url, f'req2.url={req2.url}'
            Actor.log.info(f'Queue 1 request: {req1.url}')
            Actor.log.info(f'Queue 2 request: {req2.url}')
            Actor.log.info('Queue isolation verified successfully')

            # Clean up
            await rq1.mark_request_as_handled(req1)
            await rq2.mark_request_as_handled(req2)

            # Drop queues
            await rq1.drop()
            await rq2.drop()
            Actor.log.info('Dropped both queues')

    actor = await make_actor(label='rq-isolation-test', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'
