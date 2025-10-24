from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from apify import Actor

if TYPE_CHECKING:
    from .conftest import MakeActorFunction, RunActorFunction


async def test_actor_start_remaining_timeout(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test that correct timeout is set when using `RemainingTime` value for the `timeout` argument.

    In this test, one Actor starts itself again and checks that the timeout is correctly set on the second Actor run.
    Timeout should be the remaining time of the first Actor run calculated at the moment of the other Actor start."""

    async def main() -> None:
        from datetime import datetime, timezone

        async with Actor:
            actor_input = (await Actor.get_input()) or {}
            if actor_input.get('called_from_another_actor', False) is True:
                # If this Actor run was started with a specific argument (the second Actor run), return immediately.
                # Asserts checking the timeout are in the first Actor run.
                return

            # Start another run of this actor with timeout set to the time remaining in this actor run
            other_run_data = await Actor.call(
                actor_id=Actor.configuration.actor_id or '',
                run_input={'called_from_another_actor': True},
                timeout='RemainingTime',
            )
            assert other_run_data is not None
            try:
                # To make sure that the actor is started
                await asyncio.sleep(5)
                assert other_run_data.options is not None
                assert Actor.configuration.timeout_at is not None
                assert Actor.configuration.started_at is not None

                remaining_time_after_actor_start = Actor.configuration.timeout_at - datetime.now(tz=timezone.utc)

                assert other_run_data.options.timeout > remaining_time_after_actor_start
                assert other_run_data.options.timeout < Actor.configuration.timeout_at - Actor.configuration.started_at
            finally:
                # Make sure the other actor run is aborted
                await Actor.apify_client.run(other_run_data.id).abort()

    actor = await make_actor(label='remaining-timeout', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_actor_call_remaining_timeout(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test that correct timeout is set when using `RemainingTime` value for the `timeout` argument.

    In this test, one Actor starts itself again and checks that the timeout is correctly set on the second Actor run.
    Timeout should be the remaining time of the first Actor run calculated at the moment of the other Actor call."""

    async def main() -> None:
        from datetime import datetime, timezone

        async with Actor:
            actor_input = (await Actor.get_input()) or {}
            if actor_input.get('called_from_another_actor', False) is True:
                # If this Actor run was started with a specific argument (the second Actor run), return immediately.
                # Asserts checking the timeout are in the first Actor run.
                return

            # Start another run of this actor with timeout set to the time remaining in this actor run
            other_run_data = await Actor.call(
                actor_id=Actor.configuration.actor_id or '',
                run_input={'called_from_another_actor': True},
                timeout='RemainingTime',
            )

            assert other_run_data is not None
            try:
                # To make sure that the actor is started
                await asyncio.sleep(5)

                assert other_run_data.options is not None
                assert Actor.configuration.timeout_at is not None
                assert Actor.configuration.started_at is not None

                remaining_time_after_actor_start = Actor.configuration.timeout_at - datetime.now(tz=timezone.utc)

                assert other_run_data.options.timeout > remaining_time_after_actor_start
                assert other_run_data.options.timeout < Actor.configuration.timeout_at - Actor.configuration.started_at
            finally:
                # Make sure the other actor run is aborted
                await Actor.apify_client.run(other_run_data.id).abort()

    actor = await make_actor(label='remaining-timeout', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'
