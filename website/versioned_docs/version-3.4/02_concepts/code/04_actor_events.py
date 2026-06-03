import asyncio
from typing import Any

from apify import Actor, Event


async def main() -> None:
    async with Actor:
        total_items = 1000

        # Load the state if it's saved from some previous execution
        processed_items = 0
        actor_state = await Actor.get_value('STATE')
        if actor_state is not None:
            processed_items = actor_state

        # Save the state when the `PERSIST_STATE` event happens
        async def save_state(event_data: Any) -> None:
            nonlocal processed_items
            Actor.log.info('Saving Actor state', extra=event_data)
            await Actor.set_value('STATE', processed_items)

        Actor.on(Event.PERSIST_STATE, save_state)

        # Do some fake work
        for i in range(processed_items, total_items):
            Actor.log.info(f'Processing item {i}...')
            processed_items = i
            await asyncio.sleep(0.1)

        # Suppose we can stop saving the state now
        Actor.off(Event.PERSIST_STATE, save_state)

        # Do some more fake work, this time something that can't be restarted,
        # so no point persisting the state
        for j in range(10):
            Actor.log.info(f'Processing item {j} of another kind...')
            await asyncio.sleep(1)


if __name__ == '__main__':
    asyncio.run(main())
