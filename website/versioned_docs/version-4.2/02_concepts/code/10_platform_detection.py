import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        if Actor.is_at_home():
            Actor.log.info('Running on the Apify platform')
        else:
            Actor.log.info('Running locally')


if __name__ == '__main__':
    asyncio.run(main())
