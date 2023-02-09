import asyncio

from apify import Actor
from apify.consts import ActorEventType

from .conftest import ActorFactory


class TestActorEvents:

    async def test_interval_events(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            import os
            from typing import Any, Callable

            from apify.consts import ActorEventType, ApifyEnvVars

            os.environ[ApifyEnvVars.PERSIST_STATE_INTERVAL_MILLIS] = '900'

            def on_event(event_type: ActorEventType) -> Callable:
                async def log_event(data: Any) -> None:
                    await Actor.push_data({'event_type': event_type, 'data': data})
                return log_event

            async with Actor:
                Actor.on(ActorEventType.SYSTEM_INFO, on_event(ActorEventType.SYSTEM_INFO))
                Actor.on(ActorEventType.PERSIST_STATE, on_event(ActorEventType.PERSIST_STATE))
                await asyncio.sleep(10)

        actor = await make_actor('actor-interval-events', main_func=main)

        run_result = await actor.call()

        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'
        dataset_items_page = await actor.last_run().dataset().list_items()
        persist_state_events = [item for item in dataset_items_page.items if item['event_type'] == ActorEventType.PERSIST_STATE]
        system_info_events = [item for item in dataset_items_page.items if item['event_type'] == ActorEventType.SYSTEM_INFO]
        assert len(persist_state_events) > 2
        assert len(system_info_events) > 0

    async def test_off_event(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            import os

            from apify.consts import ActorEventType, ApifyEnvVars

            os.environ[ApifyEnvVars.PERSIST_STATE_INTERVAL_MILLIS] = '100'

            counter = 0

            def count_event(data):  # type: ignore
                nonlocal counter
                print(data)
                counter += 1

            async with Actor:
                Actor.on(ActorEventType.PERSIST_STATE, count_event)
                await asyncio.sleep(0.5)
                assert counter > 1
                last_count = counter
                Actor.off(ActorEventType.PERSIST_STATE, count_event)
                await asyncio.sleep(0.5)
                assert counter == last_count

        actor = await make_actor('actor-off-event', main_func=main)

        run = await actor.call()

        assert run is not None
        assert run['status'] == 'SUCCEEDED'
