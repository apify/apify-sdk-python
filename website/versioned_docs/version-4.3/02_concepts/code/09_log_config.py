import asyncio
import logging

from apify.log import ActorLogFormatter


async def main() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(ActorLogFormatter())

    apify_logger = logging.getLogger('apify')
    apify_logger.setLevel(logging.DEBUG)
    apify_logger.addHandler(handler)


if __name__ == '__main__':
    asyncio.run(main())
