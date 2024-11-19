from __future__ import annotations

import traceback
from typing import TYPE_CHECKING

from apify._configuration import Configuration
from apify.apify_storage_client import ApifyStorageClient

try:
    from scrapy import Spider
    from scrapy.core.scheduler import BaseScheduler
    from scrapy.utils.reactor import is_asyncio_reactor_installed

    if TYPE_CHECKING:
        from scrapy.http.request import Request
except ImportError as exc:
    raise ImportError(
        'To use this module, you need to install the "scrapy" extra. Run "pip install apify[scrapy]".',
    ) from exc

from crawlee._utils.crypto import crypto_random_object_id

from apify import Actor
from apify.scrapy.requests import to_apify_request, to_scrapy_request
from apify.scrapy.utils import nested_event_loop
from apify.storages import RequestQueue


class ApifyScheduler(BaseScheduler):
    """A Scrapy scheduler that uses the Apify Request Queue to manage requests.

    This scheduler requires the asyncio Twisted reactor to be installed.
    """

    def __init__(self) -> None:
        """Create a new instance."""
        if not is_asyncio_reactor_installed():
            raise ValueError(
                f'{ApifyScheduler.__qualname__} requires the asyncio Twisted reactor. '
                'Make sure you have it configured in the TWISTED_REACTOR setting. See the asyncio '
                'documentation of Scrapy for more information.',
            )
        self._rq: RequestQueue | None = None
        self.spider: Spider | None = None

    def open(self, spider: Spider) -> None:  # this has to be named "open"
        """Open the scheduler.

        Args:
            spider: The spider that the scheduler is associated with.
        """
        self.spider = spider

        async def open_queue() -> RequestQueue:
            custom_loop_apify_client = ApifyStorageClient(configuration=Configuration.get_global_configuration())
            return await RequestQueue.open(storage_client=custom_loop_apify_client)

        try:
            self._rq = nested_event_loop.run_until_complete(open_queue())
        except BaseException:
            traceback.print_exc()
            raise

    def has_pending_requests(self) -> bool:
        """Check if the scheduler has any pending requests.

        Returns:
            True if the scheduler has any pending requests, False otherwise.
        """
        if not isinstance(self._rq, RequestQueue):
            raise TypeError('self._rq must be an instance of the RequestQueue class')

        try:
            is_finished = nested_event_loop.run_until_complete(self._rq.is_finished())
        except BaseException:
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
        call_id = crypto_random_object_id(8)
        Actor.log.debug(f'[{call_id}]: ApifyScheduler.enqueue_request was called (scrapy_request={request})...')

        if not isinstance(self.spider, Spider):
            raise TypeError('self.spider must be an instance of the Spider class')

        apify_request = to_apify_request(request, spider=self.spider)
        if apify_request is None:
            Actor.log.error(f'Request {request} was not enqueued because it could not be converted to Apify request.')
            return False

        Actor.log.debug(f'[{call_id}]: scrapy_request was transformed to apify_request (apify_request={apify_request})')

        if not isinstance(self._rq, RequestQueue):
            raise TypeError('self._rq must be an instance of the RequestQueue class')

        try:
            result = nested_event_loop.run_until_complete(self._rq.add_request(apify_request))
        except BaseException:
            traceback.print_exc()
            raise

        Actor.log.debug(f'[{call_id}]: rq.add_request.result={result}...')
        return bool(result.was_already_present)

    def next_request(self) -> Request | None:
        """Fetch the next request from the scheduler.

        Returns:
            The next request, or None if there are no more requests.
        """
        call_id = crypto_random_object_id(8)
        Actor.log.debug(f'[{call_id}]: ApifyScheduler.next_request was called...')

        if not isinstance(self._rq, RequestQueue):
            raise TypeError('self._rq must be an instance of the RequestQueue class')

        # Fetch the next request from the Request Queue
        try:
            apify_request = nested_event_loop.run_until_complete(self._rq.fetch_next_request())
        except BaseException:
            traceback.print_exc()
            raise

        Actor.log.debug(
            f'[{call_id}]: a new apify_request from the scheduler was fetched (apify_request={apify_request})'
        )

        if apify_request is None:
            return None

        if not isinstance(self.spider, Spider):
            raise TypeError('self.spider must be an instance of the Spider class')

        # Let the Request Queue know that the request is being handled. Every request should be marked as handled,
        # retrying is handled by the Scrapy's RetryMiddleware.
        try:
            nested_event_loop.run_until_complete(self._rq.mark_request_as_handled(apify_request))
        except BaseException:
            traceback.print_exc()
            raise

        scrapy_request = to_scrapy_request(apify_request, spider=self.spider)
        Actor.log.debug(
            f'[{call_id}]: apify_request was transformed to the scrapy_request which is gonna be returned '
            f'(scrapy_request={scrapy_request})',
        )
        return scrapy_request
