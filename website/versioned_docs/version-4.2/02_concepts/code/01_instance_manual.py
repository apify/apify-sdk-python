import asyncio
from datetime import timedelta

from apify import Actor


async def main() -> None:
    actor = Actor(
        event_listeners_timeout=timedelta(seconds=30),
        cleanup_timeout=timedelta(seconds=30),
    )

    await actor.init()

    try:
        # Get input
        actor_input = await actor.get_input()
        actor.log.info('Actor input: %s', actor_input)

        # Your Actor logic here
        data = {'message': 'Hello from Actor!', 'input': actor_input}
        await actor.push_data(data)

        # Set status message
        await actor.set_status_message('Actor completed successfully')

    finally:
        await actor.exit()


if __name__ == '__main__':
    asyncio.run(main())
