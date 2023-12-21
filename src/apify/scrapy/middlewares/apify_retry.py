from __future__ import annotations

import traceback
from typing import TYPE_CHECKING, Any

try:
    from scrapy.downloadermiddlewares.retry import RetryMiddleware
    from scrapy.utils.response import response_status_message
except ImportError as exc:
    raise ImportError(
        'To use this module, you need to install the "scrapy" extra. Run "pip install apify[scrapy]".',
    ) from exc

from ...actor import Actor
from ..utils import nested_event_loop, open_queue_with_custom_client, to_apify_request

if TYPE_CHECKING:
    from scrapy import Spider
    from scrapy.http import Request, Response

    from ...storages import RequestQueue


class ApifyRetryMiddleware(RetryMiddleware):
    """The default Scrapy retry middleware enriched with Apify's Request Queue interaction."""

    def __init__(self: ApifyRetryMiddleware, *args: Any, **kwargs: Any) -> None:
        """Create a new instance."""
        super().__init__(*args, **kwargs)
        try:
            self._rq: RequestQueue = nested_event_loop.run_until_complete(open_queue_with_custom_client())
        except BaseException:
            traceback.print_exc()
            raise

    def process_response(
        self: ApifyRetryMiddleware,
        request: Request,
        response: Response,
        spider: Spider,
    ) -> Request | Response | None:
        """Process the response and decide whether the request should be retried.

        Args:
            request: The request that was sent.
            response: The response that was received.
            spider: The Spider that sent the request.

        Returns:
            The response, or a new request if the request should be retried.
        """
        if not isinstance(request.url, str):
            raise TypeError(f'Expected request.url to be a string, got {type(request.url)} instead.')

        # Robots requests are bypassed directly, they don't go through a Scrapy Scheduler, and also through our
        # Request Queue. Check the scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware for details.
        if request.url.endswith('robots.txt'):
            return response

        try:
            return nested_event_loop.run_until_complete(self._handle_retry_logic(request, response, spider))
        except BaseException:
            traceback.print_exc()
            raise

    def process_exception(
        self: ApifyRetryMiddleware,
        request: Request,
        exception: BaseException,
        spider: Spider,
    ) -> Request | Response | None:
        """Handle the exception and decide whether the request should be retried.

        Args:
            request: The request that encountered an exception.
            exception: The exception that occurred.
            spider: The Spider that sent the request.

        Returns:
            None: The request will not be retried.
        """
        Actor.log.debug(f'ApifyRetryMiddleware.process_exception was called (request={request}, exception={exception})...')
        apify_request = to_apify_request(request, spider=spider)

        # Unlike the default Scrapy RetryMiddleware, we do not attempt to retry requests on exception.
        # It was causing issues with the Apify request queue, because the request was not marked as handled and was
        # stucked in the request queue forever - Scrapy crawling never finished. The solution would be to completely
        # rewrite the retry logic from default RetryMiddleware.
        try:
            nested_event_loop.run_until_complete(self._rq.mark_request_as_handled(apify_request))
        except BaseException:
            traceback.print_exc()
            raise

        return None

    async def _handle_retry_logic(
        self: ApifyRetryMiddleware,
        request: Request,
        response: Response,
        spider: Spider,
    ) -> Request | Response | None:
        """Handle the retry logic of the request."""
        Actor.log.debug(f'ApifyRetryMiddleware.handle_retry_logic was called (scrapy_request={request})...')
        apify_request = to_apify_request(request, spider=spider)

        if request.meta.get('dont_retry', False):
            await self._rq.mark_request_as_handled(apify_request)
            return response

        if response.status in self.retry_http_codes:
            await self._rq.reclaim_request(apify_request)
            reason = response_status_message(response.status)
            return self._retry(request, reason, spider) or response

        await self._rq.mark_request_as_handled(apify_request)
        return response
