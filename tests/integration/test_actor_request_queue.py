from __future__ import annotations

from typing import TYPE_CHECKING

from ._utils import generate_unique_resource_name
from apify import Actor, Request

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


async def test_request_queue_had_multiple_clients_local(
    apify_client_async: ApifyClientAsync,
) -> None:
    """`RequestQueue` clients created with different `client_key` should appear as distinct clients."""
    request_queue_name = generate_unique_resource_name('request_queue')

    async with Actor:
        rq_1 = await Actor.open_request_queue(name=request_queue_name, force_cloud=True)
        await rq_1.fetch_next_request()

        # Accessed with client created explicitly with `client_key=None` should appear as distinct client
        api_client=apify_client_async.request_queue(
                request_queue_id=rq_1.id, client_key=None)
        await api_client.list_head()

        # Check that it is correctly in the RequestQueueClient metadata
        assert (await rq_1.get_metadata()).had_multiple_clients is True # Currently broken
        # Check that it is correctly in the API, TODO: This should be teste on different level, but it is not working now
        assert ((await rq_1._client._api_client.list_head())['hadMultipleClients']) is True


async def test_request_queue_not_had_multiple_clients_local() -> None:
    """Test that same `RequestQueue` created from Actor does not act as multiple clients."""
    request_queue_name = generate_unique_resource_name('request_queue')

    async with Actor:
        rq_1 = await Actor.open_request_queue(name=request_queue_name, force_cloud=True)
        # Two calls to API to create situation where different `client_key` can set `had_multiple_clients` to True
        await rq_1.fetch_next_request()
        await rq_1.fetch_next_request()

        # Check that it is correctly in the RequestQueueClient metadata
        assert (await rq_1.get_metadata()).had_multiple_clients is False
        # Check that it is correctly in the API, TODO: This should be teste on different level, but it is not working now
        assert ((await rq_1._client._api_client.list_head())['hadMultipleClients']) is False

async def test_request_queue_had_multiple_clients_platform(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        """`RequestQueue` clients created with different `client_key` should appear as distinct clients."""
        from apify_client import ApifyClientAsync
        async with Actor:
            rq_1 = await Actor.open_request_queue()
            await rq_1.fetch_next_request()

            # Accessed with client created explicitly with `client_key=None` should appear as distinct client
            api_client=ApifyClientAsync(token=Actor.configuration.token).request_queue(
                request_queue_id=rq_1.id, client_key=None)
            await api_client.list_head()

            # Check that it is correctly in the RequestQueueClient metadata
            assert (await rq_1.get_metadata()).had_multiple_clients is True # Currently broken
            # Check that it is correctly in the API, TODO: This should be teste on different level, but it is not working now
            assert ((await rq_1._client._api_client.list_head())['hadMultipleClients']) is True

    actor = await make_actor(label='rq-same-ref-default', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_request_queue_not_had_multiple_clients_platform(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        """Test that same `RequestQueue` created from Actor does not act as multiple clients."""
        async with Actor:
            rq_1 = await Actor.open_request_queue()
            # Two calls to API to create situation where different `client_key` can set `had_multiple_clients` to True
            await rq_1.fetch_next_request()
            await rq_1.fetch_next_request()

            # Check that it is correctly in the RequestQueueClient metadata
            assert (await rq_1.get_metadata()).had_multiple_clients is False
            # Check that it is correctly in the API, TODO: This should be teste on different level, but it is not working now
            assert ((await rq_1._client._api_client.list_head())['hadMultipleClients']) is False

    actor = await make_actor(label='rq-same-ref-default', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'
