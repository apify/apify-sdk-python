from __future__ import annotations

from contextlib import suppress
from logging import getLogger
from typing import TYPE_CHECKING

from scrapy import signals

from apify import Actor, Event

if TYPE_CHECKING:
    from scrapy.crawler import Crawler

logger = getLogger(__name__)


class ApifyGracefulStopExtension:
    """A Scrapy extension that stops the crawl gracefully when the Actor run is being aborted.

    A graceful abort gives the run a moment before it is killed. The extension uses it to stop the engine: no new
    requests are started, the ones in flight finish along with their callbacks and item pipelines, and the
    scheduler marks them as handled in the request queue, so resurrecting the run does not download them again.
    A migration is handled by `ApifyScheduler` instead, as the crawl must not finish on its own then.
    """

    def __init__(self, crawler: Crawler) -> None:
        self._crawler = crawler

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> ApifyGracefulStopExtension:
        """Create the extension and hook it up to the spider's lifecycle."""
        extension = cls(crawler)
        crawler.signals.connect(extension.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(extension.spider_closed, signal=signals.spider_closed)
        return extension

    def spider_opened(self) -> None:
        """Start listening for the abort of the Actor run."""
        try:
            Actor.on(Event.ABORTING, self._on_aborting)
        except RuntimeError:
            logger.warning(
                'The Actor is not initialized, so the crawl cannot be stopped gracefully when the run is aborted.'
            )

    def spider_closed(self) -> None:
        """Stop listening for the abort of the Actor run."""
        # The Actor may have exited already, in which case there is nothing left to unregister from.
        with suppress(RuntimeError):
            Actor.off(Event.ABORTING, self._on_aborting)

    async def _on_aborting(self) -> None:
        """Stop the crawler; it waits for the requests in flight and closes the scheduler, which marks them."""
        logger.info('The Actor run is being aborted: stopping the crawl gracefully.')
        await self._crawler.stop_async()
