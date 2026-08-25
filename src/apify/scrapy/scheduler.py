from __future__ import annotations

import asyncio
from datetime import timedelta
from logging import getLogger
from typing import TYPE_CHECKING, Any

from scrapy import Spider
from scrapy import __version__ as scrapy_version
from scrapy.core.scheduler import BaseScheduler
from scrapy.utils.reactor import is_asyncio_reactor_installed

from ._async_thread import AsyncThread
from .requests import to_apify_request, to_scrapy_request
from apify import Configuration
from apify.storage_clients import ApifyStorageClient
from apify.storages import RequestQueue

if TYPE_CHECKING:
    from collections.abc import Coroutine, Iterable
    from concurrent.futures import Future

    from scrapy.crawler import Crawler
    from scrapy.http.request import Request
    from twisted.internet.defer import Deferred

    from apify import Request as ApifyRequest

    InFlightRequest = tuple[ApifyRequest, Request]
    """A request handed over to Scrapy, paired with the RQ request it came from."""

logger = getLogger(__name__)


async def _gather_failures(operations: Iterable[Coroutine[Any, Any, Any]]) -> list[BaseException | None]:
    """Run RQ updates concurrently, reporting each one's failure, or `None`, in the order given.

    The whole batch costs one round trip, and one failing update neither raises nor stops the others.
    """
    outcomes = await asyncio.gather(*operations, return_exceptions=True)
    return [outcome if isinstance(outcome, BaseException) else None for outcome in outcomes]


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

        self._requests_in_flight: list[InFlightRequest] = []
        """Requests handed over to Scrapy and not resolved in the RQ yet."""

        self._pending_marks: list[tuple[list[InFlightRequest], Future]] = []
        """Batches of mark-as-handled updates dispatched off the hot path, whose outcome is not known yet."""

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

        if self._crawler is None:
            logger.warning(
                f'{ApifyScheduler.__qualname__} was built without a crawler, so it cannot see what Scrapy is '
                'still working on. Every request is marked as handled the moment it is handed over, and an '
                'interrupted run loses whatever was in flight. Build it with `from_crawler` to avoid that.'
            )
        else:
            self._verify_engine_internals()

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
                self._resolve_finished_requests(wait=True)
            except Exception:
                logger.exception('Failed to resolve the requests still in flight in the request queue.')

            # Scrapy drains its in-progress requests before closing the scheduler, so this only runs if a future
            # Scrapy closes it earlier; then they go back to the RQ as pending, in a single round trip. One failed
            # reclaim must not strand the rest either.
            if self._requests_in_flight:
                reclaims = _gather_failures(
                    rq.reclaim_request(apify_request) for apify_request, _ in self._requests_in_flight
                )
                try:
                    outcomes = self._async_thread.run_coro(reclaims)
                except Exception:
                    logger.exception('Failed to reclaim the requests still in flight in the request queue.')
                else:
                    for (apify_request, _), outcome in zip(self._requests_in_flight, outcomes, strict=True):
                        if outcome is not None:
                            logger.error(
                                f'Failed to reclaim the request {apify_request} in the request queue.',
                                exc_info=outcome,
                            )

            self._requests_in_flight.clear()

        # Closing the event loop would silently cancel the updates fired off on the hot path.
        self._async_thread.wait_for_submitted()

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

        Resolves the requests Scrapy has finished with first, as their outcome is what decides the answer.

        Returns:
            True if the scheduler has any pending requests, False otherwise.
        """
        if not isinstance(self._rq, RequestQueue):
            raise TypeError('self._rq must be an instance of the RequestQueue class')

        # Scrapy asks this only once both its downloader and its scraper are idle, so everything still tracked
        # as in flight is provably finished.
        self._resolve_finished_requests(wait=True)

        # The RQ answers from its own bookkeeping, which a pending update has not reached yet.
        self._async_thread.wait_for_submitted()

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

        # The engine polls this method throughout the crawl, so resolving here keeps the RQ current without
        # blocking on the round trips.
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

        # A corrupt or legacy payload must not crash the run, and is marked as handled right away, otherwise
        # the RQ would keep handing it back forever.
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

        # The entry stays unresolved until Scrapy is done with the request, so a run interrupted mid-flight
        # leaves it pending instead of silently handled.
        self._requests_in_flight.append((apify_request, scrapy_request))

        return scrapy_request

    def _verify_engine_internals(self) -> None:
        """Fail at open time if Scrapy's engine no longer exposes what the in-flight tracking reads.

        The hot path deliberately does not guard those undocumented internals: swallowing an `AttributeError`
        there would quietly go back to marking every request as handled the moment it is handed over. The
        scraper's slot does not exist yet when the scheduler opens, so this only proves `downloader.active` and
        `scraper.slot` are there; a missing `slot.active` surfaces from `next_request` on the first request.

        Raises:
            RuntimeError: If the engine internals the tracking relies on cannot be read.
        """
        try:
            self._requests_busy_in_scrapy()
        except AttributeError as exc:
            raise RuntimeError(
                f'{ApifyScheduler.__qualname__} cannot tell which requests Scrapy is working on: this Scrapy '
                f'version ({scrapy_version}) does not expose the engine internals it reads. Please report this '
                'at https://github.com/apify/apify-sdk-python/issues.'
            ) from exc

    def _requests_busy_in_scrapy(self) -> set[Request]:
        """Return the requests Scrapy is still working on.

        A request joins the downloader's active set before the middleware chain runs and leaves the scraper's
        only once the callback and the item pipeline are done, so absence from both means Scrapy is done with
        it - downloaded, dropped by a middleware or errored out alike.

        Without a crawler there is nothing to ask and every request reads as finished; `open` warns about that.
        """
        engine = self._crawler.engine if self._crawler is not None else None
        if engine is None:
            return set()

        scraper_slot = engine.scraper.slot
        return engine.downloader.active | (scraper_slot.active if scraper_slot is not None else set())

    def _resolve_finished_requests(self, *, wait: bool) -> None:
        """Mark every request Scrapy has finished processing as handled in the RQ.

        A whole pass reaches the RQ in a single round trip. A request whose update cannot be dispatched, or
        turns out to have failed, stays tracked for the next call to retry.

        Args:
            wait: Whether to block until the RQ has been updated. Pass False on the crawl's hot path, where
                nothing depends on the result and blocking would stall the Twisted reactor.
        """
        rq = self._rq
        if not isinstance(rq, RequestQueue) or not (self._requests_in_flight or self._pending_marks):
            return

        # Updates dispatched by an earlier pass that did not land are marked again by this one.
        finished = self._collect_failed_marks(wait=wait)
        unresolved: list[InFlightRequest] = []

        if self._requests_in_flight:
            busy = self._requests_busy_in_scrapy()
            for apify_request, scrapy_request in self._requests_in_flight:
                if scrapy_request in busy:
                    unresolved.append((apify_request, scrapy_request))
                else:
                    finished.append((apify_request, scrapy_request))

        if finished:
            marks = _gather_failures(rq.mark_request_as_handled(apify_request) for apify_request, _ in finished)
            try:
                if wait:
                    unresolved.extend(self._failed_marks(finished, self._async_thread.run_coro(marks)))
                else:
                    self._pending_marks.append((finished, self._async_thread.submit_coro(marks)))
            except Exception:
                logger.exception(f'Failed to mark {len(finished)} request(s) as handled in the request queue.')
                unresolved.extend(finished)

        self._requests_in_flight = unresolved

    def _collect_failed_marks(self, *, wait: bool) -> list[InFlightRequest]:
        """Return the requests whose already dispatched mark-as-handled did not land, so it can be retried.

        `submit_coro` reports nothing back to the reactor thread, so an update failing after dispatch would
        otherwise drop its request from the tracking and leave it in progress in the RQ forever, which would
        keep the RQ from ever reporting itself finished.

        Args:
            wait: Whether to block until every dispatched update has finished. Updates still running are kept
                for the next call.
        """
        if not self._pending_marks:
            return []

        if wait:
            self._async_thread.wait_for_submitted()

        failed: list[InFlightRequest] = []
        pending: list[tuple[list[InFlightRequest], Future]] = []

        for requests, future in self._pending_marks:
            if not future.done():
                pending.append((requests, future))
            elif future.cancelled():
                logger.error(f'Marking {len(requests)} request(s) as handled was cancelled before it finished.')
                failed.extend(requests)
            else:
                # `_gather_failures` reports a failed update in its result rather than raising, so an exception
                # here means the dispatch itself did not survive the event loop being torn down under it.
                try:
                    outcomes = future.result()
                except Exception:
                    logger.exception(f'Failed to mark {len(requests)} request(s) as handled in the request queue.')
                    failed.extend(requests)
                else:
                    failed.extend(self._failed_marks(requests, outcomes))

        self._pending_marks = pending

        return failed

    @staticmethod
    def _failed_marks(
        requests: list[InFlightRequest],
        outcomes: list[BaseException | None],
    ) -> list[InFlightRequest]:
        """Pair a batch of updates back with their requests, returning and logging the ones that failed."""
        failed = []

        for (apify_request, scrapy_request), outcome in zip(requests, outcomes, strict=True):
            if outcome is not None:
                logger.error(
                    f'Failed to mark the request {apify_request} as handled in the request queue.',
                    exc_info=outcome,
                )
                failed.append((apify_request, scrapy_request))

        return failed
