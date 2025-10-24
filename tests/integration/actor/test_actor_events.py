from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from apify_shared.consts import ActorEventTypes

from apify import Actor

if TYPE_CHECKING:
    from .conftest import MakeActorFunction, RunActorFunction


async def test_emit_and_capture_interval_events(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        # TC003 - TYPE_CHECKING section is problematic for our integration tests.
        import os
        from collections.abc import Callable  # noqa: TC003
        from datetime import datetime
        from typing import Any

        from apify_shared.consts import ActorEventTypes, ApifyEnvVars
        from crawlee.events._types import Event, EventSystemInfoData

        os.environ[ApifyEnvVars.PERSIST_STATE_INTERVAL_MILLIS] = '900'

        was_system_info_emitted = False
        system_infos = list[EventSystemInfoData]()

        def on_event(event_type: ActorEventTypes) -> Callable:
            async def log_event(data: Any) -> None:
                nonlocal was_system_info_emitted
                nonlocal system_infos
                print(f'Got actor event ({event_type=}, {data=})')
                await Actor.push_data({'event_type': event_type, 'data': data})
                if event_type == ActorEventTypes.SYSTEM_INFO:
                    was_system_info_emitted = True
                    system_infos.append(data)

            return log_event

        async with Actor:
            Actor.on(Event.SYSTEM_INFO, on_event(ActorEventTypes.SYSTEM_INFO))
            Actor.on(Event.PERSIST_STATE, on_event(ActorEventTypes.PERSIST_STATE))
            await asyncio.sleep(3)

            # The SYSTEM_INFO event sometimes takes a while to appear, let's wait for it for a while longer.
            for _ in range(20):
                if was_system_info_emitted:
                    break
                await asyncio.sleep(1)

            # Check that parsing datetimes works correctly.
            # Check `createdAt` is a datetime (so it's the same locally and on platform).
            assert isinstance(system_infos[0].cpu_info.created_at, datetime)

    actor = await make_actor(label='actor-interval-events', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'

    dataset_items_page = await actor.last_run().dataset().list_items()
    persist_state_events = [
        item for item in dataset_items_page.items if item['event_type'] == ActorEventTypes.PERSIST_STATE
    ]
    system_info_events = [
        item for item in dataset_items_page.items if item['event_type'] == ActorEventTypes.SYSTEM_INFO
    ]
    assert len(persist_state_events) > 2
    assert len(system_info_events) > 0


async def test_event_listener_can_be_removed_successfully(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        import os
        from typing import Any

        from apify_shared.consts import ApifyEnvVars
        from crawlee.events._types import Event

        os.environ[ApifyEnvVars.PERSIST_STATE_INTERVAL_MILLIS] = '100'

        counter = 0

        def count_event(data: Any) -> None:
            nonlocal counter
            print(data)
            counter += 1

        async with Actor:
            Actor.on(Event.PERSIST_STATE, count_event)
            await asyncio.sleep(0.5)
            assert counter > 1
            last_count = counter
            Actor.off(Event.PERSIST_STATE, count_event)
            await asyncio.sleep(0.5)
            assert counter == last_count

    actor = await make_actor(label='actor-off-event', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'
