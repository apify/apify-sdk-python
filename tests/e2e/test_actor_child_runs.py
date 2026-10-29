from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING

from apify import Actor
from apify._child_runs import CHILD_RUNS_KEY

if TYPE_CHECKING:
    from apify_client import ApifyClientAsync

    from .conftest import MakeActorFunction, RunActorFunction


async def test_named_child_run_is_reattached_after_reboot(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """A named child run started before a reboot is listed after it and reattached by a named call."""

    async def main() -> None:
        async with Actor:
            actor_input = (await Actor.get_input()) or {}
            if actor_input.get('is_child') is True:
                await asyncio.sleep(20)
                return

            actor_id = Actor.configuration.actor_id or ''
            child_run_id = await Actor.get_value('child_run_id')

            if child_run_id is None:
                run = await Actor.start(actor_id=actor_id, run_input={'is_child': True}, run_name='child')
                await Actor.set_value('child_run_id', run.id)
                await Actor.reboot()
                return

            child_runs = Actor.child_runs
            assert child_runs.keys() == {'child'}, f'child_runs={child_runs}'
            assert child_runs['child'].resource_id == child_run_id, f'child_runs={child_runs}'

            run = await Actor.call(actor_id=actor_id, run_input={'is_child': True}, run_name='child')
            assert run is not None, 'run is None'
            assert run.id == child_run_id, f'run.id={run.id}, child_run_id={child_run_id}'
            assert run.status == 'SUCCEEDED', f'run.status={run.status}'

    actor = await make_actor(label='child-run-reattach', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'
    # The parent run and the one child run it reattached to.
    assert (await actor.runs().list()).total == 2


async def test_named_aborted_child_run_is_resurrected_after_reboot(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """A named child run aborted before a reboot is resurrected by a named start after it."""

    async def main() -> None:
        async with Actor:
            actor_input = (await Actor.get_input()) or {}
            if actor_input.get('is_child') is True:
                await asyncio.sleep(300)
                return

            actor_id = Actor.configuration.actor_id or ''
            child_run_id = await Actor.get_value('child_run_id')

            if child_run_id is None:
                run = await Actor.start(actor_id=actor_id, run_input={'is_child': True}, run_name='child')
                await Actor.set_value('child_run_id', run.id)
                run_client = Actor.apify_client.run(run.id)
                await run_client.abort()
                aborted_run = await run_client.wait_for_finish()
                assert aborted_run is not None, 'aborted_run is None'
                assert aborted_run.status == 'ABORTED', f'aborted_run.status={aborted_run.status}'
                await Actor.reboot()
                return

            run = await Actor.start(actor_id=actor_id, run_input={'is_child': True}, run_name='child')
            try:
                assert run.id == child_run_id, f'run.id={run.id}, child_run_id={child_run_id}'
                assert run.status in {'READY', 'RUNNING'}, f'run.status={run.status}'
            finally:
                await Actor.apify_client.run(run.id).abort()

    actor = await make_actor(label='child-run-resurrect', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'
    # The parent run and the one child run it resurrected.
    assert (await actor.runs().list()).total == 2


async def test_named_child_run_is_aborted_with_parent(
    make_actor: MakeActorFunction,
    apify_client_async: ApifyClientAsync,
) -> None:
    """A named child run started with `abort_with_parent` is aborted when the parent is gracefully aborted."""

    async def main() -> None:
        async with Actor:
            actor_input = (await Actor.get_input()) or {}
            if actor_input.get('is_child') is True:
                await asyncio.sleep(300)
                return

            actor_id = Actor.configuration.actor_id or ''
            await Actor.start(actor_id=actor_id, run_input={'is_child': True}, run_name='child', abort_with_parent=True)
            await asyncio.sleep(300)

    actor = await make_actor(label='child-run-abort-with-parent', main_func=main)
    parent_run = await actor.start()
    parent_kvs = apify_client_async.key_value_store(parent_run.default_key_value_store_id)

    # Wait for the parent to record the child run.
    for _ in range(60):
        if record := await parent_kvs.get_record(CHILD_RUNS_KEY):
            break
        await asyncio.sleep(2)
    else:
        raise AssertionError('The parent run did not record the child run in time.')

    child_run_id = record['value']['child']['runId']
    parent_run_client = apify_client_async.run(parent_run.id)
    await parent_run_client.abort(gracefully=True)
    await parent_run_client.wait_for_finish(wait_duration=timedelta(seconds=120))

    child_run = await apify_client_async.run(child_run_id).wait_for_finish(wait_duration=timedelta(seconds=120))
    assert child_run is not None
    assert child_run.status == 'ABORTED'
