import asyncio

from apify import Actor
from apify.consts import ActorEventTypes

from .conftest import ActorFactory


class TestActorEvents:

    async def test_interval_events(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            import os
            from typing import Any, Callable

            from apify.consts import ActorEventTypes, ApifyEnvVars

            os.environ[ApifyEnvVars.PERSIST_STATE_INTERVAL_MILLIS] = '900'

            was_system_info_emitted = False

            def on_event(event_type: ActorEventTypes) -> Callable:
                async def log_event(data: Any) -> None:
                    nonlocal was_system_info_emitted
                    print(f'Got actor event ({event_type=}, {data=})')
                    await Actor.push_data({'event_type': event_type, 'data': data})
                    if event_type == ActorEventTypes.SYSTEM_INFO:
                        was_system_info_emitted = True
                return log_event

            async with Actor:
                Actor.on(ActorEventTypes.SYSTEM_INFO, on_event(ActorEventTypes.SYSTEM_INFO))
                Actor.on(ActorEventTypes.PERSIST_STATE, on_event(ActorEventTypes.PERSIST_STATE))
                await asyncio.sleep(3)

                # The SYSTEM_INFO event sometimes takes a while to appear, let's wait for it for a while longer
                for _ in range(20):
                    if was_system_info_emitted:
                        break
                    await asyncio.sleep(1)

        actor = await make_actor('actor-interval-events', main_func=main)

        run_result = await actor.call()

        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'
        dataset_items_page = await actor.last_run().dataset().list_items()
        persist_state_events = [item for item in dataset_items_page.items if item['event_type'] == ActorEventTypes.PERSIST_STATE]
        system_info_events = [item for item in dataset_items_page.items if item['event_type'] == ActorEventTypes.SYSTEM_INFO]
        assert len(persist_state_events) > 2
        assert len(system_info_events) > 0

    async def test_off_event(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            import os

            from apify.consts import ActorEventTypes, ApifyEnvVars

            os.environ[ApifyEnvVars.PERSIST_STATE_INTERVAL_MILLIS] = '100'

            counter = 0

            def count_event(data):  # type: ignore
                nonlocal counter
                print(data)
                counter += 1

            async with Actor:
                Actor.on(ActorEventTypes.PERSIST_STATE, count_event)
                await asyncio.sleep(0.5)
                assert counter > 1
                last_count = counter
                Actor.off(ActorEventTypes.PERSIST_STATE, count_event)
                await asyncio.sleep(0.5)
                assert counter == last_count

        actor = await make_actor('actor-off-event', main_func=main)

        run = await actor.call()

        assert run is not None
        assert run['status'] == 'SUCCEEDED'
