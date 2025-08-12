from __future__ import annotations

from typing import TYPE_CHECKING

from apify_shared.consts import ApifyEnvVars

from ._utils import generate_unique_resource_name
from apify import Actor, Request

if TYPE_CHECKING:
    import pytest

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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert apify_client_async.token is not None
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_client_async.token)

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


async def test_request_queue_is_finished(
    apify_client_async: ApifyClientAsync,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert apify_client_async.token is not None
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_client_async.token)

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


async def test_same_request_fetched_twice(
    apify_client_async: ApifyClientAsync,
    monkeypatch: pytest.MonkeyPatch):
    """Test that the same request can be fetched twice from the request queue."""
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_client_async.token)

    request_queue_name = generate_unique_resource_name('request_queue')
    async with Actor:
        try:
            request_queue = await Actor.open_request_queue(name='same-request-fetch', force_cloud=request_queue_name)

            request = Request.from_url('http://example.com')
            await request_queue.add_request(request)

            fetched_request_1 = await request_queue.fetch_next_request()
            assert fetched_request_1 is not None
            assert fetched_request_1.url == 'http://example.com'
            await request_queue.reclaim_request(fetched_request_1)
        finally:
            await request_queue.drop()
