from __future__ import annotations

import traceback
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
    from scrapy.http.request import Request
    from twisted.internet.defer import Deferred

logger = getLogger(__name__)


class ApifyScheduler(BaseScheduler):
    """A Scrapy scheduler that uses the Apify `RequestQueue` to manage requests.

    This scheduler requires the asyncio Twisted reactor to be installed.
    """

    def __init__(self) -> None:
        if not is_asyncio_reactor_installed():
            raise ValueError(
                f'{ApifyScheduler.__qualname__} requires the asyncio Twisted reactor. '
                'Make sure you have it configured in the TWISTED_REACTOR setting. See the asyncio '
                'documentation of Scrapy for more information.',
            )
        self._rq: RequestQueue | None = None
        self.spider: Spider | None = None

        # A thread with the asyncio event loop to run coroutines on.
        self._async_thread = AsyncThread()

        # Track consecutive None responses to detect stale cache
        self._consecutive_none_count = 0
        self._max_consecutive_none = 3  # Reduced from 5 to exit faster
        self._max_cache_refresh_attempts = 2  # Reduced from 3 to exit faster
        self._cache_refresh_attempts = 0
        self._queue_exhausted = False

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
            traceback.print_exc()
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
        # If we've determined the queue is exhausted, always return False
        if self._queue_exhausted:
            logger.debug('Queue is exhausted, reporting no pending requests')
            return False

        if not isinstance(self._rq, RequestQueue):
            raise TypeError('self._rq must be an instance of the RequestQueue class')

        try:
            is_finished = self._async_thread.run_coro(self._rq.is_finished())
        except Exception:
            traceback.print_exc()
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
            traceback.print_exc()
            raise

        logger.debug(f'rq.add_request result: {result}')
        return bool(result.was_already_present)

    def next_request(self) -> Request | None:
        """Fetch the next request from the scheduler.

        Returns:
            The next request, or None if there are no more requests.
        """
        logger.debug('next_request called...')
        if not isinstance(self._rq, RequestQueue):
            raise TypeError('self._rq must be an instance of the RequestQueue class')

        # If we've already determined the queue is exhausted, don't keep trying
        if self._queue_exhausted:
            logger.debug('Queue previously determined to be exhausted, returning None')
            return None

        max_retries = 3
        for attempt in range(max_retries):
            try:
                apify_request = self._async_thread.run_coro(self._rq.fetch_next_request())
            except Exception:
                traceback.print_exc()
                if attempt < max_retries - 1:
                    logger.warning(f'Attempt {attempt + 1} failed, retrying...')
                    continue
                raise

            logger.debug(f'Fetched apify_request: {apify_request}')
            if apify_request is None:
                self._consecutive_none_count += 1

                # If we get too many consecutive None responses, force cache refresh
                if (
                    self._consecutive_none_count >= self._max_consecutive_none
                    and self._cache_refresh_attempts < self._max_cache_refresh_attempts
                ):
                    self._cache_refresh_attempts += 1
                    logger.warning(
                        f'Got {self._consecutive_none_count} consecutive None responses, '
                        f'forcing cache refresh (attempt '
                        f'{self._cache_refresh_attempts}/{self._max_cache_refresh_attempts})'
                    )
                    try:
                        client = getattr(self._rq, '_client', None)
                        if client and hasattr(client, '_should_check_for_forefront_requests'):
                            client._should_check_for_forefront_requests = True  # noqa: SLF001
                            logger.debug('Set _should_check_for_forefront_requests to force refresh')
                        # Reset counter after forcing refresh
                        self._consecutive_none_count = 0
                        # Try one more time after forcing refresh
                        apify_request = self._async_thread.run_coro(self._rq.fetch_next_request())
                        logger.debug(f'Fetched apify_request after forced refresh: {apify_request}')
                    except Exception as e:
                        logger.debug(f'Failed to force cache refresh: {e}')

                # If still None after retries, mark queue as exhausted
                if apify_request is None:
                    if self._cache_refresh_attempts >= self._max_cache_refresh_attempts:
                        logger.info(
                            'Queue appears to be exhausted after multiple cache refresh attempts. Marking as complete.'
                        )
                        self._queue_exhausted = True
                    return None
            else:
                # Reset counter when we get a valid request
                self._consecutive_none_count = 0

            if not isinstance(self.spider, Spider):
                raise TypeError('self.spider must be an instance of the Spider class')

            # Let the request queue know that the request is being handled. Every request should
            # be marked as handled, retrying is handled by the Scrapy's RetryMiddleware.
            try:
                result = self._async_thread.run_coro(self._rq.mark_request_as_handled(apify_request))

                # Force head refresh if request was successfully marked as handled
                # This helps prevent cache inconsistency issues where the head points to stale request IDs
                if result is not None:
                    try:
                        # Access the client to force head refresh on next fetch (only for Apify cloud clients)
                        client = getattr(self._rq, '_client', None)
                        if client and hasattr(client, '_should_check_for_forefront_requests'):
                            client._should_check_for_forefront_requests = True  # noqa: SLF001
                            logger.debug('Forcing head refresh after successful mark_request_as_handled')
                    except Exception:
                        # Ignore errors in head refresh - it's an optimization, not critical
                        logger.debug('Failed to force head refresh - continuing normally')

            except Exception:
                traceback.print_exc()
                if attempt < max_retries - 1:
                    logger.warning('Failed to mark request as handled, retrying...')
                    continue
                raise

            scrapy_request = to_scrapy_request(apify_request, spider=self.spider)
            logger.debug(f'Converted to scrapy_request: {scrapy_request}')
            return scrapy_request

        return None
