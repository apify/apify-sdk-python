from __future__ import annotations

import asyncio
import threading
import traceback
from concurrent import futures
from logging import getLogger
from typing import TYPE_CHECKING, Any

from scrapy import Spider
from scrapy.core.scheduler import BaseScheduler
from scrapy.utils.reactor import is_asyncio_reactor_installed

from apify import Configuration
from apify.apify_storage_client import ApifyStorageClient
from apify.scrapy.requests import to_apify_request, to_scrapy_request
from apify.storages import RequestQueue

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from scrapy.http.request import Request
    from twisted.internet.defer import Deferred

logger = getLogger(__name__)

_TIMEOUT = 60
"""The timeout for waiting on asyncio coroutines to finish."""


def _start_event_loop(eventloop: asyncio.AbstractEventLoop) -> None:
    """Set and run the event loop until it is stopped.

    Args:
        eventloop: The asyncio event loop to run.
    """
    asyncio.set_event_loop(eventloop)
    try:
        eventloop.run_forever()
    finally:
        eventloop.close()
        logger.debug('Asyncio event loop has been closed.')


def _run_async_coro(eventloop: asyncio.AbstractEventLoop, coro: Coroutine) -> Any:
    """Run a coroutine on the given loop in our separate thread, waiting for its result.

    Args:
        eventloop: The asyncio event loop to run the coroutine on.
        coro: The coroutine to run.

    Returns:
        The result of the coroutine.
    """
    if not eventloop.is_running():
        logger.warning('Event loop is not running! Ignoring coroutine execution.')
        return None

    future = asyncio.run_coroutine_threadsafe(coro, eventloop)
    try:
        return future.result(timeout=_TIMEOUT)
    except futures.TimeoutError as exc:
        logger.exception('Coroutine execution timed out.', exc_info=exc)
        raise
    except Exception as exc:
        logger.exception('Coroutine execution raised an exception.', exc_info=exc)
        raise


async def _shutdown_async_tasks(eventloop: asyncio.AbstractEventLoop) -> None:
    """Cancel and wait for all pending tasks on the current event loop.

    Args:
        eventloop: The asyncio event loop to cancel tasks on.
    """
    tasks = [task for task in asyncio.all_tasks(eventloop) if task is not asyncio.current_task()]
    if not tasks:
        return
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


def _force_exit_event_loop(eventloop: asyncio.AbstractEventLoop, thread: threading.Thread) -> None:
    """Forcefully shut down the event loop and its thread.

    Args:
        eventloop: The asyncio event loop to stop.
        thread: The thread running the event loop.
    """
    try:
        logger.info('Forced shutdown of the event loop and its thread...')
        eventloop.call_soon_threadsafe(eventloop.stop)
        thread.join(timeout=5)
    except Exception as exc:
        logger.exception('Exception occurred during forced event loop shutdown.', exc_info=exc)


class ApifyScheduler(BaseScheduler):
    """A Scrapy scheduler that uses the Apify request queue to manage requests.

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

        # Create a new event loop and run it in a separate thread.
        self._eventloop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=lambda: _start_event_loop(self._eventloop), daemon=True)
        self._thread.start()

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
            self._rq = _run_async_coro(self._eventloop, open_rq())
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
            if self._eventloop.is_running():
                # Cancel all pending tasks in the event loop.
                _run_async_coro(self._eventloop, _shutdown_async_tasks(self._eventloop))

            # Stop the event loop.
            self._eventloop.call_soon_threadsafe(self._eventloop.stop)

            # Wait for the event loop thread to exit.
            self._thread.join(timeout=_TIMEOUT)

            # If the thread is still alive, execute a forced shutdown.
            if self._thread.is_alive():
                logger.warning('Event loop thread did not exit cleanly! Forcing shutdown...')
                _force_exit_event_loop(self._eventloop, self._thread)

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
            is_finished = _run_async_coro(self._eventloop, self._rq.is_finished())
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
            result = _run_async_coro(self._eventloop, self._rq.add_request(apify_request))
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
            apify_request = _run_async_coro(self._eventloop, self._rq.fetch_next_request())
        except Exception:
            traceback.print_exc()
            raise

        logger.debug(f'Fetched apify_request: {apify_request}')
        if apify_request is None:
            return None

        if not isinstance(self.spider, Spider):
            raise TypeError('self.spider must be an instance of the Spider class')

        # Let the request queue know that the request is being handled. Every request should be marked as handled,
        # retrying is handled by the Scrapy's RetryMiddleware.
        try:
            _run_async_coro(self._eventloop, self._rq.mark_request_as_handled(apify_request))
        except Exception:
            traceback.print_exc()
            raise

        scrapy_request = to_scrapy_request(apify_request, spider=self.spider)
        logger.debug(f'Converted to scrapy_request: {scrapy_request}')
        return scrapy_request
