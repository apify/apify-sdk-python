import asyncio

import pytest

from apify import Actor
from tests.integration.conftest import MakeActorFunction, RunActorFunction


async def test_actor_start_remaining_timeout(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        async with Actor:
            actor_input = (await Actor.get_input()) or {}
            if actor_input.get("called_from_another_actor",False) is True:
                # Do nothing and only wait for
                await asyncio.sleep(1000)
                return


            self_run_client = Actor.apify_client.run(Actor.configuration.actor_run_id)
            self_run_data_1 = await self_run_client.get()
            run_time_1 = self_run_data_1.get('runTimeSecs', 0)
            self_timeout = self_run_data_1.get('options', {}).get('timeoutSecs', 0)

            # Start another run of this actor with timeout set to the time remaining in this actor
            other_run_data = await Actor.start(actor_id=Actor.configuration.actor_id,
                                               run_input={"called_from_another_actor": True},
                                               timeout="RemainingTime")

            self_run_data_2 = await self_run_client.get()
            run_time_2 = self_run_data_2.get('runTimeSecs', 0)
            other_actor_timeout = other_run_data.get('options', {}).get('timeoutSecs', 0)

            assert other_actor_timeout > self_timeout - run_time_1
            assert other_actor_timeout < self_timeout - run_time_2

    actor = await make_actor(label='remaining timeout', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'
