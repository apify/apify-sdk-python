from __future__ import annotations

import logging

from crawlee._log_config import CrawleeLogFormatter

# Name of the logger used throughout the library (resolves to 'apify')
logger_name = __name__.split('.')[0]

# Logger used throughout the library
logger = logging.getLogger(logger_name)


class ActorLogFormatter(CrawleeLogFormatter):  # noqa: D101 Inherited from parent class
    pass
