from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ._utils import generate_unique_resource_name
from apify import Actor, Request
from apify._models import ActorRun

if TYPE_CHECKING:
    from apify_client import ApifyClientAsync
    from crawlee.storages import RequestQueue

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


async def test_force_cloud(
    apify_client_async: ApifyClientAsync,
) -> None:
    request_queue_name = generate_unique_resource_name('request_queue')

    async with Actor:
        request_queue = await Actor.open_request_queue(name=request_queue_name, force_cloud=True)
        request_queue_id = (await request_queue.get_metadata()).id

        request_info = await request_queue.add_request(Request.from_url('http://example.com'))

    request_queue_client = apify_client_async.request_queue(request_queue_id)

    try:
        request_queue_details = await request_queue_client.get()
        assert request_queue_details is not None
        assert request_queue_details.get('name') == request_queue_name

        request_queue_request = await request_queue_client.get_request(request_info.id)
        assert request_queue_request is not None
        assert request_queue_request['url'] == 'http://example.com'
    finally:
        await request_queue_client.delete()


async def test_request_queue_is_finished() -> None:
    request_queue_name = generate_unique_resource_name('request_queue')

    async with Actor:
        try:
            request_queue = await Actor.open_request_queue(name=request_queue_name, force_cloud=True)
            await request_queue.add_request(Request.from_url('http://example.com'))
            assert not await request_queue.is_finished()

            request = await request_queue.fetch_next_request()
            assert request is not None
            assert not await request_queue.is_finished(), (
                'RequestQueue should not be finished unless the request is marked as handled.'
            )

            await request_queue.mark_request_as_handled(request)
            assert await request_queue.is_finished()
        finally:
            await request_queue.drop()


async def test_request_queue_enhanced_metadata(
    request_queue_force_cloud: RequestQueue,
    apify_client_async: ApifyClientAsync,
) -> None:
    """Test metadata tracking.

    Multiple clients scenarios are not guaranteed to give correct results without delay. But at least multiple clients,
    single producer, should be reliable on the producer side."""

    for i in range(1, 10):
        await request_queue_force_cloud.add_request(Request.from_url(f'http://example.com/{i}'))
        # Reliable information as the API response is enhanced with local metadata estimation.
        assert (await request_queue_force_cloud.get_metadata()).total_request_count == i

    # Accessed with client created explicitly with `client_key=None` should appear as distinct client
    api_client = apify_client_async.request_queue(request_queue_id=request_queue_force_cloud.id, client_key=None)
    await api_client.list_head()

    # The presence of another non-producing client should not affect the metadata
    for i in range(10, 20):
        await request_queue_force_cloud.add_request(Request.from_url(f'http://example.com/{i}'))
        # Reliable information as the API response is enhanced with local metadata estimation.
        assert (await request_queue_force_cloud.get_metadata()).total_request_count == i


async def test_request_queue_metadata_another_client(
    request_queue_force_cloud: RequestQueue,
    apify_client_async: ApifyClientAsync,
) -> None:
    """Test metadata tracking. The delayed metadata should be reliable even when changed by another client."""
    api_client = apify_client_async.request_queue(request_queue_id=request_queue_force_cloud.id, client_key=None)
    await api_client.add_request(Request.from_url('http://example.com/1').model_dump(by_alias=True, exclude={'id'}))

    # Wait to be sure that the API has updated the global metadata
    await asyncio.sleep(10)

    assert (await request_queue_force_cloud.get_metadata()).total_request_count == 1


async def test_request_queue_had_multiple_clients_local(
    request_queue_force_cloud: RequestQueue,
    apify_client_async: ApifyClientAsync,
) -> None:
    """Test that `RequestQueue` correctly detects multiple clients.

    Clients created with different `client_key` should appear as distinct clients."""
    await request_queue_force_cloud.fetch_next_request()

    # Accessed with client created explicitly with `client_key=None` should appear as distinct client
    api_client = apify_client_async.request_queue(request_queue_id=request_queue_force_cloud.id, client_key=None)
    await api_client.list_head()

    # Check that it is correctly in the RequestQueueClient metadata
    assert (await request_queue_force_cloud.get_metadata()).had_multiple_clients is True

    # Check that it is correctly in the API
    api_response = await api_client.get()
    assert api_response
    assert api_response['hadMultipleClients'] is True


async def test_request_queue_not_had_multiple_clients_local(
    request_queue_force_cloud: RequestQueue, apify_client_async: ApifyClientAsync
) -> None:
    """Test that same `RequestQueue` created from Actor does not act as multiple clients."""

    # Two calls to API to create situation where different `client_key` can set `had_multiple_clients` to True
    await request_queue_force_cloud.fetch_next_request()
    await request_queue_force_cloud.fetch_next_request()

    # Check that it is correctly in the RequestQueueClient metadata
    assert (await request_queue_force_cloud.get_metadata()).had_multiple_clients is False

    # Check that it is correctly in the API
    api_client = apify_client_async.request_queue(request_queue_id=request_queue_force_cloud.id)
    api_response = await api_client.get()
    assert api_response
    assert api_response['hadMultipleClients'] is False


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
