from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

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

        from crawlee.events._types import Event, EventSystemInfoData

        from apify import ActorEventTypes
        from apify._consts import ApifyEnvVars

        os.environ[ApifyEnvVars.PERSIST_STATE_INTERVAL_MILLIS] = '900'

        was_system_info_emitted = False
        system_infos = list[EventSystemInfoData]()

        def on_event(event_type: ActorEventTypes) -> Callable:
            async def log_event(data: Any) -> None:
                nonlocal was_system_info_emitted
                nonlocal system_infos
                print(f'Got actor event ({event_type=}, {data=})')
                await Actor.push_data({'event_type': event_type, 'data': data})
                if event_type == 'systemInfo':
                    was_system_info_emitted = True
                    system_infos.append(data)

            return log_event

        async with Actor:
            Actor.on(Event.SYSTEM_INFO, on_event('systemInfo'))
            Actor.on(Event.PERSIST_STATE, on_event('persistState'))
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
    persist_state_events = [item for item in dataset_items_page.items if item['event_type'] == 'persistState']
    system_info_events = [item for item in dataset_items_page.items if item['event_type'] == 'systemInfo']
    assert len(persist_state_events) > 2
    assert len(system_info_events) > 0


async def test_event_listener_can_be_removed_successfully(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        import os

        from crawlee.events._types import Event

        from apify._consts import ApifyEnvVars

        os.environ[ApifyEnvVars.PERSIST_STATE_INTERVAL_MILLIS] = '100'

        # `removed_count` is bumped by the listener we later remove. `total_count` is bumped by a
        # reference listener that stays subscribed the whole time and acts as a heartbeat, letting the
        # test wait for real events instead of guessing wall-clock durations. Both listeners are async
        # so they run on the event loop and can drive `heartbeat` safely.
        removed_count = 0
        total_count = 0
        heartbeat = asyncio.Event()

        async def removed_listener() -> None:
            nonlocal removed_count
            removed_count += 1

        async def reference_listener() -> None:
            nonlocal total_count
            total_count += 1
            heartbeat.set()

        async def wait_for_events(n: int) -> None:
            """Block until the reference listener has observed at least `n` more events."""
            target = total_count + n
            while total_count < target:
                heartbeat.clear()
                if total_count >= target:
                    return
                await heartbeat.wait()

        async with Actor:
            Actor.on(Event.PERSIST_STATE, removed_listener)
            Actor.on(Event.PERSIST_STATE, reference_listener)

            # Both listeners are live: wait until the one we will remove has demonstrably received events.
            while removed_count < 2:
                await wait_for_events(1)

            Actor.off(Event.PERSIST_STATE, removed_listener)

            # One more event cycle flushes any invocation dispatched just before `off`, then snapshot.
            await wait_for_events(1)
            count_after_off = removed_count

            # Over several further event cycles, the removed listener must not be called again.
            await wait_for_events(5)
            assert removed_count == count_after_off

    actor = await make_actor(label='actor-off-event', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'
