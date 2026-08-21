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

    from apify import Request as ApifyRequest

logger = getLogger(__name__)


class ApifyScheduler(BaseScheduler):
    """A Scrapy scheduler that uses the Apify `RequestQueue` to manage requests.

    This scheduler requires the asyncio Twisted reactor to be installed.
    """

    def __init__(
        self,
        async_thread_timeout: timedelta = timedelta(seconds=60),
        crawler: Crawler | None = None,
    ) -> None:
        if not is_asyncio_reactor_installed():
            raise ValueError(
                f'{ApifyScheduler.__qualname__} requires the asyncio Twisted reactor. '
                'Make sure you have it configured in the TWISTED_REACTOR setting. See the asyncio '
                'documentation of Scrapy for more information.',
            )
        self._rq: RequestQueue | None = None
        self.spider: Spider | None = None
        self._crawler = crawler

        self._requests_in_flight: list[tuple[ApifyRequest, Request]] = []
        """Requests handed over to Scrapy and not resolved in the request queue yet."""

        # A thread with the asyncio event loop to run coroutines on.
        self._async_thread = AsyncThread(default_timeout=async_thread_timeout)

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> ApifyScheduler:
        """Create the scheduler, reading the async-thread timeout from the Scrapy settings.

        The `APIFY_ASYNC_THREAD_TIMEOUT_SECS` setting (in seconds) caps how long each coroutine run on the
        background event loop may take before timing out; it defaults to 60 seconds.
        """
        timeout_secs = crawler.settings.getint('APIFY_ASYNC_THREAD_TIMEOUT_SECS', 60)
        return cls(async_thread_timeout=timedelta(seconds=timeout_secs), crawler=crawler)

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

        Resolve the requests Scrapy still holds, then shut down the event loop and its thread gracefully.

        Args:
            reason: The reason for closing the spider.
        """
        logger.debug(f'Closing {self.__class__.__name__} due to {reason}...')

        rq = self._rq
        if isinstance(rq, RequestQueue):
            try:
                # Resolve what Scrapy holds while the event loop is still around. Whatever it did not finish -
                # an interrupted run, an Actor migration - goes back to the queue, so the next run picks it up
                # instead of waiting for its lock to expire.
                self._resolve_finished_requests(wait=True)
                for apify_request, _ in self._requests_in_flight:
                    self._async_thread.run_coro(rq.reclaim_request(apify_request))
                self._requests_in_flight.clear()
            except Exception:
                logger.exception('Failed to resolve the requests still in flight in the request queue.')

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

        # Scrapy asks this only once both its downloader and its scraper are idle, so everything still tracked
        # as in flight is provably finished. Wait for those updates to land: the queue reports itself unfinished
        # while any request it handed out is still unresolved.
        self._resolve_finished_requests(wait=True)

        # Log here before re-raising: this coroutine ran on a separate event-loop thread, and the failure is
        # otherwise easy to lose as it crosses that thread boundary back into Scrapy's synchronous machinery.
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
        if not isinstance(self.spider, Spider):
            raise TypeError('self.spider must be an instance of the Spider class')

        apify_request = to_apify_request(request, spider=self.spider)
        if apify_request is None:
            logger.warning(f'Request {request} could not be converted to Apify request; skipping it.')
            return False

        if not isinstance(self._rq, RequestQueue):
            raise TypeError('self._rq must be an instance of the RequestQueue class')

        # Log here before re-raising: this coroutine ran on a separate event-loop thread, and the failure is
        # otherwise easy to lose as it crosses that thread boundary back into Scrapy's synchronous machinery.
        try:
            result = self._async_thread.run_coro(self._rq.add_request(apify_request))
        except Exception:
            logger.exception('Failed to enqueue the request to the request queue.')
            raise

        return not bool(result.was_already_present)

    def next_request(self) -> Request | None:
        """Fetch the next request from the scheduler.

        Returns:
            The next request, or None if there are no more requests.
        """
        if not isinstance(self._rq, RequestQueue):
            raise TypeError('self._rq must be an instance of the RequestQueue class')

        # Resolve whatever Scrapy has finished since the last call. The engine polls this method throughout the
        # crawl, which keeps the queue's view of progress current without blocking on the round trips.
        self._resolve_finished_requests(wait=False)

        # Log here before re-raising: this coroutine ran on a separate event-loop thread, and the failure is
        # otherwise easy to lose as it crosses that thread boundary back into Scrapy's synchronous machinery.
        try:
            apify_request = self._async_thread.run_coro(self._rq.fetch_next_request())
        except Exception:
            logger.exception('Failed to fetch the next request from the request queue.')
            raise

        if apify_request is None:
            return None

        if not isinstance(self.spider, Spider):
            raise TypeError('self.spider must be an instance of the Spider class')

        # A malformed entry must not crash the whole run, so on failure it is logged and skipped rather than
        # propagating. Such an unrecoverable entry (a corrupt or legacy payload) is marked as handled right
        # away, otherwise the queue would keep handing it back forever.
        try:
            scrapy_request = to_scrapy_request(apify_request, spider=self.spider)
        except Exception as exc:
            logger.warning(f'Failed to convert Apify request {apify_request} to a Scrapy request; skipping it: {exc}')
            try:
                self._async_thread.run_coro(self._rq.mark_request_as_handled(apify_request))
            except Exception:
                logger.exception('Failed to mark the request as handled in the request queue.')
                raise
            return None

        # The entry stays unresolved in the queue until Scrapy is done with the request, so a run interrupted
        # mid-flight leaves it pending instead of silently handled.
        self._requests_in_flight.append((apify_request, scrapy_request))

        return scrapy_request

    def _requests_busy_in_scrapy(self) -> set[Request]:
        """Return the requests Scrapy is still working on.

        A request handed out by `next_request` stays in the downloader's or the scraper's active set until its
        download, the downloader middleware chain and the spider callback have all finished, so absence from
        both means Scrapy is done with it. Requests a middleware drops before the download reach neither set,
        but Scrapy only asks `has_pending_requests` once both are empty, which is what settles those too.
        """
        engine = self._crawler.engine if self._crawler is not None else None
        if engine is None:
            return set()

        scraper_slot = engine.scraper.slot
        return engine.downloader.active | (scraper_slot.active if scraper_slot is not None else set())

    def _resolve_finished_requests(self, *, wait: bool) -> None:
        """Mark every request Scrapy has finished processing as handled in the request queue.

        Args:
            wait: Whether to block until the queue has been updated. Pass False on the crawl's hot path, where
                nothing depends on the result and blocking would stall the Twisted reactor.
        """
        rq = self._rq
        if not self._requests_in_flight or not isinstance(rq, RequestQueue):
            return

        busy = self._requests_busy_in_scrapy()
        still_in_flight = []

        for apify_request, scrapy_request in self._requests_in_flight:
            if scrapy_request in busy:
                still_in_flight.append((apify_request, scrapy_request))
            elif wait:
                self._async_thread.run_coro(rq.mark_request_as_handled(apify_request))
            else:
                self._async_thread.submit_coro(rq.mark_request_as_handled(apify_request))

        self._requests_in_flight = still_in_flight
