from __future__ import annotations

import asyncio
import threading
from concurrent import futures
from datetime import timedelta
from logging import getLogger
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Coroutine

logger = getLogger(__name__)


class AsyncThread:
    """Class for running an asyncio event loop in a separate thread.

    This allows running asynchronous coroutines from synchronous code by executingthem on an event loop
    that runs in its own dedicated thread.
    """

    def __init__(self) -> None:
        self._eventloop = asyncio.new_event_loop()

        # Start the event loop in a dedicated daemon thread.
        self._thread = threading.Thread(
            target=self._start_event_loop,
            daemon=True,
        )
        self._thread.start()

    def run_coro(
        self,
        coro: Coroutine,
        timeout: timedelta = timedelta(seconds=60),
    ) -> Any:
        """Run a coroutine on an event loop running in a separate thread.

        This method schedules the coroutine to run on the event loop and blocks until the coroutine completes
        or the specified timeout is reached.

        Args:
            coro: The coroutine to run.
            timeout: The maximum number of seconds to wait for the coroutine to finish.

        Returns:
            The result returned by the coroutine.

        Raises:
            RuntimeError: If the event loop is not running.
            TimeoutError: If the coroutine does not complete within the timeout.
            Exception: Any exception raised during coroutine execution.
        """
        if not self._eventloop.is_running():
            raise RuntimeError(f'The coroutine {coro} cannot be executed because the event loop is not running.')

        # Submit the coroutine to the event loop running in the other thread.
        future = asyncio.run_coroutine_threadsafe(coro, self._eventloop)
        try:
            # Wait for the coroutine's result until the specified timeout.
            return future.result(timeout=timeout.total_seconds())
        except futures.TimeoutError as exc:
            logger.exception('Coroutine execution timed out.', exc_info=exc)
            raise
        except Exception as exc:
            logger.exception('Coroutine execution raised an exception.', exc_info=exc)
            raise

    def close(self, timeout: timedelta = timedelta(seconds=60)) -> None:
        """Close the event loop and its thread gracefully.

        This method cancels all pending tasks, stops the event loop, and waits for the thread to exit.
        If the thread does not exit within the given timeout, a forced shutdown is attempted.

        Args:
            timeout: The maximum number of seconds to wait for the event loop thread to exit.
        """
        if self._eventloop.is_running():
            # Cancel all pending tasks in the event loop.
            self.run_coro(self._shutdown_tasks())

        # Schedule the event loop to stop.
        self._eventloop.call_soon_threadsafe(self._eventloop.stop)

        # Wait for the event loop thread to finish execution.
        self._thread.join(timeout=timeout.total_seconds())

        # If the thread is still running after the timeout, force a shutdown.
        if self._thread.is_alive():
            logger.warning('Event loop thread did not exit cleanly! Forcing shutdown...')
            self._force_exit_event_loop()

    def _start_event_loop(self) -> None:
        """Set up and run the asyncio event loop in the dedicated thread."""
        asyncio.set_event_loop(self._eventloop)
        try:
            self._eventloop.run_forever()
        finally:
            self._eventloop.close()
            logger.debug('Asyncio event loop has been closed.')

    async def _shutdown_tasks(self) -> None:
        """Cancel all pending tasks in the event loop."""
        # Retrieve all tasks for the event loop, excluding the current task.
        tasks = [task for task in asyncio.all_tasks(self._eventloop) if task is not asyncio.current_task()]

        # Cancel each pending task.
        for task in tasks:
            task.cancel()

        # Wait until all tasks have been cancelled or finished.
        await asyncio.gather(*tasks, return_exceptions=True)

    def _force_exit_event_loop(self) -> None:
        """Shut down the event loop and its thread forcefully."""
        try:
            logger.info('Forced shutdown of the event loop and its thread...')
            self._eventloop.call_soon_threadsafe(self._eventloop.stop)
            self._thread.join(timeout=5)
        except Exception as exc:
            logger.exception('Exception occurred during forced event loop shutdown.', exc_info=exc)
