from __future__ import annotations

from datetime import timedelta
from logging import getLogger
from typing import TYPE_CHECKING

from scrapy import Spider
from scrapy.core.scheduler import BaseScheduler
from scrapy.utils.reactor import is_asyncio_reactor_installed

from ._async_thread import AsyncThread
from .requests import to_apify_request, to_scrapy_request
from apify import Configuration
from apify.storage_clients import ApifyStorageClient
from apify.storages import RequestQueue

if TYPE_CHECKING:
    from scrapy.crawler import Crawler
    from scrapy.http.request import Request
    from twisted.internet.defer import Deferred

logger = getLogger(__name__)


class ApifyScheduler(BaseScheduler):
    """A Scrapy scheduler that uses the Apify `RequestQueue` to manage requests.

    This scheduler requires the asyncio Twisted reactor to be installed.
    """

    def __init__(self, async_thread_timeout: timedelta = timedelta(seconds=60)) -> None:
        if not is_asyncio_reactor_installed():
            raise ValueError(
                f'{ApifyScheduler.__qualname__} requires the asyncio Twisted reactor. '
                'Make sure you have it configured in the TWISTED_REACTOR setting. See the asyncio '
                'documentation of Scrapy for more information.',
            )
        self._rq: RequestQueue | None = None
        self.spider: Spider | None = None

        # A thread with the asyncio event loop to run coroutines on.
        self._async_thread = AsyncThread(default_timeout=async_thread_timeout)

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> ApifyScheduler:
        """Create the scheduler, reading the async-thread timeout from the Scrapy settings.

        The `APIFY_ASYNC_THREAD_TIMEOUT_SECS` setting (in seconds) caps how long each coroutine run on the
        background event loop may take before timing out; it defaults to 60 seconds.
        """
        timeout_secs = crawler.settings.getint('APIFY_ASYNC_THREAD_TIMEOUT_SECS', 60)
        return cls(async_thread_timeout=timedelta(seconds=timeout_secs))

    def open(self, spider: Spider) -> Deferred[None] | None:
        """Open the scheduler.

        Args:
            spider: The spider that the scheduler is associated with.
        """
        self.spider = spider

        async def open_rq() -> RequestQueue:
            configuration = Configuration.get_global_configuration()
            if configuration.is_at_home:
                storage_client = ApifyStorageClient()
                return await RequestQueue.open(
                    configuration=configuration,
                    storage_client=storage_client,
                )
            return await RequestQueue.open()

        try:
            self._rq = self._async_thread.run_coro(open_rq())
        except Exception:
            logger.exception('Failed to open the request queue.')
            # Close the freshly started async thread so a failed open does not leak its event-loop thread.
            # Guard the close so a secondary failure here cannot mask the original error.
            try:
                self._async_thread.close()
            except Exception:
                logger.exception('Failed to close the async thread after a failed scheduler open.')
            raise

        return None

    def close(self, reason: str) -> None:
        """Close the scheduler.

        Shut down the event loop and its thread gracefully.

        Args:
            reason: The reason for closing the spider.
        """
        logger.debug(f'Closing {self.__class__.__name__} due to {reason}...')
        try:
            self._async_thread.close()

        except KeyboardInterrupt:
            logger.warning('Shutdown interrupted by KeyboardInterrupt!')

        except Exception:
            logger.exception('Exception occurred while shutting down.')

        finally:
            logger.debug(f'{self.__class__.__name__} closed successfully.')

    def has_pending_requests(self) -> bool:
        """Check if the scheduler has any pending requests.

        Returns:
            True if the scheduler has any pending requests, False otherwise.
        """
        if not isinstance(self._rq, RequestQueue):
            raise TypeError('self._rq must be an instance of the RequestQueue class')

        try:
            is_finished = self._async_thread.run_coro(self._rq.is_finished())
        except Exception:
            logger.exception('Failed to check whether the request queue is finished.')
            raise

        return not is_finished

    def enqueue_request(self, request: Request) -> bool:
        """Add a request to the scheduler.

        This could be called from either from a spider or a downloader middleware (e.g. redirect, retry, ...).

        Args:
            request: The request to add to the scheduler.

        Returns:
            True if the request was successfully enqueued, False otherwise.
        """
        logger.debug(f'ApifyScheduler.enqueue_request was called (scrapy_request={request})...')

        if not isinstance(self.spider, Spider):
            raise TypeError('self.spider must be an instance of the Spider class')

        apify_request = to_apify_request(request, spider=self.spider)
        if apify_request is None:
            logger.error(f'Request {request} could not be converted to Apify request.')
            return False

        logger.debug(f'Converted to apify_request: {apify_request}')
        if not isinstance(self._rq, RequestQueue):
            raise TypeError('self._rq must be an instance of the RequestQueue class')

        try:
            result = self._async_thread.run_coro(self._rq.add_request(apify_request))
        except Exception:
            logger.exception('Failed to enqueue the request to the request queue.')
            raise

        logger.debug(f'rq.add_request result: {result}')
        return not bool(result.was_already_present)

    def next_request(self) -> Request | None:
        """Fetch the next request from the scheduler.

        Returns:
            The next request, or None if there are no more requests.
        """
        logger.debug('next_request called...')
        if not isinstance(self._rq, RequestQueue):
            raise TypeError('self._rq must be an instance of the RequestQueue class')

        try:
            apify_request = self._async_thread.run_coro(self._rq.fetch_next_request())
        except Exception:
            logger.exception('Failed to fetch the next request from the request queue.')
            raise

        logger.debug(f'Fetched apify_request: {apify_request}')
        if apify_request is None:
            return None

        if not isinstance(self.spider, Spider):
            raise TypeError('self.spider must be an instance of the Spider class')

        # Reconstruct the Scrapy request before consuming the queue entry. A malformed entry must not crash
        # the whole run, so on failure it is logged and skipped (None) rather than propagating.
        try:
            scrapy_request = to_scrapy_request(apify_request, spider=self.spider)
        except Exception:
            logger.exception(f'Failed to convert Apify request {apify_request} to a Scrapy request; skipping it.')
            scrapy_request = None

        # Mark the request as handled. This runs even when reconstruction failed above: an unrecoverable entry
        # (a corrupt or legacy payload) must still be consumed, otherwise the queue would keep handing it back
        # forever. Retrying genuine failures is the RetryMiddleware's job.
        try:
            self._async_thread.run_coro(self._rq.mark_request_as_handled(apify_request))
        except Exception:
            logger.exception('Failed to mark the request as handled in the request queue.')
            raise

        if scrapy_request is None:
            return None

        logger.debug(f'Converted to scrapy_request: {scrapy_request}')
        return scrapy_request
