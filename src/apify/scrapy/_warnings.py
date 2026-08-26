from __future__ import annotations

import logging

from crawlee._utils.log import LoggerOnce

logger_once = LoggerOnce(logging.getLogger(__name__))
"""Process-wide deduplication: the scheduler and the graceful-stop extension share the one message below."""


def warn_about_uninitialized_actor() -> None:
    """Warn, once per process, that the integration cannot react to the Actor run being migrated or aborted.

    The scheduler and the graceful-stop extension both need an initialized Actor to listen for its events, and both
    run without one in a plain `scrapy crawl`. One message covers them both.
    """
    logger_once.log(
        'The Actor is not initialized, so the Scrapy integration cannot react to a migration or an abort of the '
        'Actor run; the requests Scrapy is working on when the run is interrupted stay pending in the request queue.',
        key='uninitialized-actor',
        level=logging.WARNING,
    )
