import asyncio
from datetime import timedelta

from apify import Actor, Configuration, Event


async def main() -> None:
    configuration = Configuration(
        persist_state_interval=timedelta(seconds=10)
        # Set other configuration options here as needed.
    )

    async with Actor(configuration=configuration):
        # Define a handler that will be called for every persist state event.
        async def save_state() -> None:
            await Actor.set_value('STATE', 'Hello, world!')

        # The save_state handler will be called every 10 seconds now.
        Actor.on(Event.PERSIST_STATE, save_state)


if __name__ == '__main__':
    asyncio.run(main())
