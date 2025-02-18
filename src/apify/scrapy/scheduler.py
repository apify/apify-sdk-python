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
from apify.apify_storage_client import ApifyStorageClient
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

    def open(self, spider: Spider) -> Deferred[None] | None:
        """Open the scheduler.

        Args:
            spider: The spider that the scheduler is associated with.
        """
        self.spider = spider

        async def open_rq() -> RequestQueue:
            config = Configuration.get_global_configuration()
            if config.is_at_home:
                storage_client = ApifyStorageClient.from_config(config)
                return await RequestQueue.open(storage_client=storage_client)
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

        try:
            apify_request = self._async_thread.run_coro(self._rq.fetch_next_request())
        except Exception:
            traceback.print_exc()
            raise

        logger.debug(f'Fetched apify_request: {apify_request}')
        if apify_request is None:
            return None

        if not isinstance(self.spider, Spider):
            raise TypeError('self.spider must be an instance of the Spider class')

        # Let the request queue know that the request is being handled. Every request should
        # be marked as handled, retrying is handled by the Scrapy's RetryMiddleware.
        try:
            self._async_thread.run_coro(self._rq.mark_request_as_handled(apify_request))
        except Exception:
            traceback.print_exc()
            raise

        scrapy_request = to_scrapy_request(apify_request, spider=self.spider)
        logger.debug(f'Converted to scrapy_request: {scrapy_request}')
        return scrapy_request
