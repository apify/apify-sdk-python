import asyncio
import logging

from apify_client._logging import _DebugLogFormatter

from .main import main

client_logger = logging.getLogger('apify_client')
if not client_logger.hasHandlers():
    client_logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    handler.setFormatter(_DebugLogFormatter())
    client_logger.addHandler(handler)

asyncio.run(main())
