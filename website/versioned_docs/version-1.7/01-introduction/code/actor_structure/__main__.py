import asyncio
import logging

from apify.log import ActorLogFormatter

from .main import main

handler = logging.StreamHandler()
handler.setFormatter(ActorLogFormatter())

apify_logger = logging.getLogger('apify')
apify_logger.setLevel(logging.DEBUG)
apify_logger.addHandler(handler)

asyncio.run(main())
