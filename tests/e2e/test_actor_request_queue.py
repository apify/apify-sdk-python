from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from apify import Actor
from apify._models import ActorRun

if TYPE_CHECKING:
    from apify_client import ApifyClientAsync

    from .conftest import MakeActorFunction, RunActorFunction


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
        raw_run_result = await run_client.wait_for_finish(wait_duration=timedelta(seconds=600))
        assert raw_run_result is not None

        run_result = ActorRun.from_client_actor_run(raw_run_result)
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
