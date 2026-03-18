import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        # Get input
        actor_input = await Actor.get_input()
        Actor.log.info('Actor input: %s', actor_input)

        # Your Actor logic here
        data = {'message': 'Hello from Actor!', 'input': actor_input}
        await Actor.push_data(data)

        # Set status message
        await Actor.set_status_message('Actor completed successfully')


if __name__ == '__main__':
    asyncio.run(main())
