from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from apify import Actor

if TYPE_CHECKING:
    from .conftest import MakeActorFunction, RunActorFunction


async def test_named_child_run_is_reattached_after_reboot(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """A named child run started before a reboot is reattached and awaited by a named call after it."""

    async def main() -> None:
        async with Actor:
            actor_input = (await Actor.get_input()) or {}
            if actor_input.get('is_child') is True:
                await asyncio.sleep(20)
                return

            actor_id = Actor.configuration.actor_id or ''
            child_run_id = await Actor.get_value('child_run_id')

            if child_run_id is None:
                run = await Actor.start(actor_id=actor_id, run_input={'is_child': True}, name='child')
                await Actor.set_value('child_run_id', run.id)
                await Actor.reboot()
                return

            run = await Actor.call(actor_id=actor_id, run_input={'is_child': True}, name='child')
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
                run = await Actor.start(actor_id=actor_id, run_input={'is_child': True}, name='child')
                await Actor.set_value('child_run_id', run.id)
                run_client = Actor.apify_client.run(run.id)
                await run_client.abort()
                aborted_run = await run_client.wait_for_finish()
                assert aborted_run is not None, 'aborted_run is None'
                assert aborted_run.status == 'ABORTED', f'aborted_run.status={aborted_run.status}'
                await Actor.reboot()
                return

            run = await Actor.start(actor_id=actor_id, run_input={'is_child': True}, name='child')
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
