from __future__ import annotations

import traceback

try:
    from scrapy import Spider
    from scrapy.core.scheduler import BaseScheduler
    from scrapy.http.request import Request  # noqa: TCH002
    from scrapy.utils.reactor import is_asyncio_reactor_installed
except ImportError as exc:
    raise ImportError(
        'To use this module, you need to install the "scrapy" extra. Run "pip install apify[scrapy]".',
    ) from exc

from .._crypto import crypto_random_object_id
from ..actor import Actor
from ..storages import RequestQueue
from .utils import nested_event_loop, open_queue_with_custom_client, to_apify_request, to_scrapy_request


class ApifyScheduler(BaseScheduler):
    """A Scrapy scheduler that uses the Apify Request Queue to manage requests.

    This scheduler requires the asyncio Twisted reactor to be installed.
    """

    def __init__(self: ApifyScheduler) -> None:
        """Create a new instance."""
        if not is_asyncio_reactor_installed():
            raise ValueError(
                f'{ApifyScheduler.__qualname__} requires the asyncio Twisted reactor. '
                'Make sure you have it configured in the TWISTED_REACTOR setting. See the asyncio '
                'documentation of Scrapy for more information.',
            )
        self._rq: RequestQueue | None = None
        self.spider: Spider | None = None

    def open(self: ApifyScheduler, spider: Spider) -> None:  # noqa: A003 # this has to be named "open"
        """Open the scheduler.

        Args:
            spider: The spider that the scheduler is associated with.
        """
        self.spider = spider

        try:
            self._rq = nested_event_loop.run_until_complete(open_queue_with_custom_client())
        except BaseException:
            traceback.print_exc()
            raise

    def close(self: ApifyScheduler, reason: str) -> None:
        """Close the scheduler.

        Args:
            reason: The reason for closing the scheduler.
        """
        Actor.log.debug(f'ApifyScheduler.close was called (reason={reason})...')
        nested_event_loop.stop()
        nested_event_loop.close()

    def has_pending_requests(self: ApifyScheduler) -> bool:
        """Check if the scheduler has any pending requests.

        Returns:
            True if the scheduler has any pending requests, False otherwise.
        """
        assert isinstance(self._rq, RequestQueue)  # noqa: S101
        try:
            is_finished = nested_event_loop.run_until_complete(self._rq.is_finished())
        except BaseException:
            traceback.print_exc()
            raise

        return not is_finished

    def enqueue_request(self: ApifyScheduler, request: Request) -> bool:
        """Add a request to the scheduler.

        Args:
            request: The request to add to the scheduler.

        Returns:
            True if the request was successfully enqueued, False otherwise.
        """
        call_id = crypto_random_object_id(8)
        Actor.log.debug(f'[{call_id}]: ApifyScheduler.enqueue_request was called (scrapy_request={request})...')

        assert isinstance(self.spider, Spider)  # noqa: S101
        apify_request = to_apify_request(request, spider=self.spider)
        Actor.log.debug(f'[{call_id}]: scrapy_request was transformed to apify_request (apify_request={apify_request})')
        assert isinstance(self._rq, RequestQueue)  # noqa: S101

        try:
            result = nested_event_loop.run_until_complete(self._rq.add_request(apify_request))
        except BaseException:
            traceback.print_exc()
            raise

        Actor.log.debug(f'[{call_id}]: apify_request was added to the RQ (apify_request={apify_request})')
        return bool(result['wasAlreadyPresent'])

    def next_request(self: ApifyScheduler) -> Request | None:
        """Fetch the next request from the scheduler.

        Returns:
            The next request, or None if there are no more requests.
        """
        call_id = crypto_random_object_id(8)
        Actor.log.debug(f'[{call_id}]: ApifyScheduler.next_request was called...')
        assert isinstance(self._rq, RequestQueue)  # noqa: S101

        try:
            apify_request = nested_event_loop.run_until_complete(self._rq.fetch_next_request())
        except BaseException:
            traceback.print_exc()
            raise

        Actor.log.debug(f'[{call_id}]: a new apify_request from the scheduler was fetched (apify_request={apify_request})')

        if apify_request is None:
            return None

        assert isinstance(self.spider, Spider)  # noqa: S101
        scrapy_request = to_scrapy_request(apify_request, spider=self.spider)
        Actor.log.debug(
            f'[{call_id}]: apify_request was transformed to the scrapy_request which is gonna be returned (scrapy_request={scrapy_request})',
        )
        return scrapy_request
