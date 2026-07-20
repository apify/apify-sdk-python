import asyncio
import logging

from apify import Actor


async def main() -> None:
    async with Actor:
        # Default redirect logger
        await Actor.call(actor_id='some_actor_id')
        # No redirect logger
        await Actor.call(actor_id='some_actor_id', logger=None)
        # Custom redirect logger
        await Actor.call(
            actor_id='some_actor_id',
            logger=logging.getLogger('custom_logger'),
        )


if __name__ == '__main__':
    asyncio.run(main())
