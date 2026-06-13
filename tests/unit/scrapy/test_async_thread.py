from __future__ import annotations

import asyncio
import logging
import threading
from concurrent import futures
from datetime import timedelta
from typing import Any, Literal

import pytest

from ..._utils import poll_until_condition
from apify.scrapy._async_thread import AsyncThread


def _wait_until_running(thread: AsyncThread, timeout: float = 2.0) -> None:
    """Block until the background event loop is running, so `run_coro` does not race the thread startup."""
    if not asyncio.run(poll_until_condition(thread._eventloop.is_running, timeout=timeout, poll_interval=0.01)):
        raise AssertionError('The event loop did not start in time.')


def test_run_coro_cancels_the_coroutine_on_timeout() -> None:
    """A timed-out coroutine is cancelled, not left running on the background loop."""
    thread = AsyncThread()
    _wait_until_running(thread)

    started = threading.Event()
    cancelled = threading.Event()

    async def slow() -> None:
        started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    with pytest.raises(futures.TimeoutError):
        thread.run_coro(slow(), timeout=timedelta(seconds=0.1))

    assert started.wait(timeout=2)
    assert cancelled.wait(timeout=2), 'the timed-out coroutine was left running instead of being cancelled'

    thread.close()


def test_run_coro_does_not_log_on_exception(caplog: pytest.LogCaptureFixture) -> None:
    """`run_coro` propagates a failing coroutine without logging it itself (the caller/Scrapy reports it once)."""
    thread = AsyncThread()
    _wait_until_running(thread)

    async def boom() -> None:
        raise RuntimeError('boom')

    with caplog.at_level(logging.DEBUG, logger='apify.scrapy._async_thread'), pytest.raises(RuntimeError, match='boom'):
        thread.run_coro(boom())

    thread.close()

    assert [record for record in caplog.records if record.levelno >= logging.ERROR] == []


def test_close_is_idempotent() -> None:
    """Calling `close` twice is a no-op the second time, not a `RuntimeError` on the closed loop."""
    thread = AsyncThread()
    _wait_until_running(thread)
    thread.run_coro(asyncio.sleep(0))

    thread.close()
    thread.close()  # must not raise


def test_close_passes_its_timeout_to_the_shutdown_step(monkeypatch: pytest.MonkeyPatch) -> None:
    """`close(timeout=...)` honours that timeout for the task-cancellation step, not only the thread join."""
    thread = AsyncThread()
    _wait_until_running(thread)
    thread.run_coro(asyncio.sleep(0))

    recorded: list[timedelta | str] = []
    original = thread.run_coro

    def spy(coro: Any, timeout: timedelta | Literal['default'] = 'default') -> Any:
        recorded.append(timeout)
        return original(coro, timeout=timeout)

    monkeypatch.setattr(thread, 'run_coro', spy)
    thread.close(timeout=timedelta(seconds=42))

    assert recorded == [timedelta(seconds=42)]


def test_close_stops_and_joins_thread_even_when_task_cancellation_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """If cancelling the pending tasks fails, `close` still stops the loop and joins the thread, not leaks it."""
    thread = AsyncThread()
    _wait_until_running(thread)

    async def boom() -> None:
        raise RuntimeError('shutdown boom')

    monkeypatch.setattr(thread, '_shutdown_tasks', boom)

    with pytest.raises(RuntimeError, match='shutdown boom'):
        thread.close(timeout=timedelta(seconds=5))

    # The loop was stopped and its thread joined despite the failing cancellation, so nothing is left running.
    assert not thread._thread.is_alive()
    assert thread._eventloop.is_closed()
