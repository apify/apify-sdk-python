import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input()
        Actor.log.info('Actor input: %s', actor_input)
        await Actor.set_value('OUTPUT', 'Hello, world!')
        raise RuntimeError('Ouch!')


if __name__ == '__main__':
    asyncio.run(main())
