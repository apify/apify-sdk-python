import asyncio
import logging

from apify import Actor
from apify.log import ActorLogFormatter


async def main() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(ActorLogFormatter())

    apify_logger = logging.getLogger('apify')
    apify_logger.setLevel(logging.DEBUG)
    apify_logger.addHandler(handler)

    async with Actor:
        Actor.log.debug('This is a debug message')
        Actor.log.info('This is an info message')
        Actor.log.warning('This is a warning message', extra={'reason': 'Bad Actor!'})
        Actor.log.error('This is an error message')
        try:
            raise RuntimeError('Ouch!')
        except RuntimeError:
            Actor.log.exception('This is an exceptional message')


if __name__ == '__main__':
    asyncio.run(main())
