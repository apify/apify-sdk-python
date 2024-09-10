from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from crawlee._log_config import CrawleeLogFormatter, configure_logger, get_configured_log_level

if TYPE_CHECKING:
    from apify import Configuration

# Name of the logger used throughout the library (resolves to 'apify')
logger_name = __name__.split('.')[0]

# Logger used throughout the library
logger = logging.getLogger(logger_name)


class ActorLogFormatter(CrawleeLogFormatter):  # noqa: D101 Inherited from parent class
    pass


def _configure_logging(configuration: Configuration) -> None:
    apify_client_logger = logging.getLogger('apify_client')
    configure_logger(apify_client_logger, configuration, remove_old_handlers=True)

    level = get_configured_log_level(configuration)

    # Keep apify_client logger quiet unless debug logging is requested
    if level > logging.DEBUG:
        apify_client_logger.setLevel(logging.INFO)
    else:
        apify_client_logger.setLevel(level)

    # Silence HTTPX logger unless debug logging is requested
    httpx_logger = logging.getLogger('httpx')
    if level > logging.DEBUG:
        httpx_logger.setLevel(logging.WARNING)
    else:
        httpx_logger.setLevel(level)

    # Use configured log level for apify logger
    apify_logger = logging.getLogger('apify')
    configure_logger(apify_logger, configuration, remove_old_handlers=True)
