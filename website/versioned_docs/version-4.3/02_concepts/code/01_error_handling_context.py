import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        # Any unhandled exception triggers Actor.fail() automatically
        raise RuntimeError('Boom')


if __name__ == '__main__':
    asyncio.run(main())
