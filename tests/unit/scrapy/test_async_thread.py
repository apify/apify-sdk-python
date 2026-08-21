from __future__ import annotations

import asyncio
import logging
import threading
import time
from concurrent import futures
from datetime import timedelta
from typing import Any, Literal

import pytest

from ..._utils import poll_until_condition
from apify.scrapy._async_thread import SUBMITTED_PRUNE_THRESHOLD, AsyncThread


async def _return(value: int) -> int:
    return value


def _wait_until_running(thread: AsyncThread, timeout: float = 2.0) -> None:
    """Block until the background event loop is running, so `run_coro` does not race the thread startup."""
    if not asyncio.run(poll_until_condition(thread._eventloop.is_running, timeout=timeout, poll_interval=0.01)):
        raise AssertionError('The event loop did not start in time.')


def test_run_coro_returns_coroutine_result() -> None:
    """`run_coro` runs a coroutine on the background loop and returns its result."""
    async_thread = AsyncThread()
    try:
        assert async_thread.run_coro(_return(42)) == 42
    finally:
        async_thread.close()


def test_run_coro_succeeds_when_called_before_loop_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    """`run_coro` must not fail when invoked before the background thread reaches `run_forever`."""
    gate = threading.Event()
    original_start = AsyncThread._start_event_loop

    def gated_start(self: AsyncThread) -> None:
        gate.wait()  # hold the loop just shy of run_forever() to force the startup race
        original_start(self)

    monkeypatch.setattr(AsyncThread, '_start_event_loop', gated_start)

    async_thread = AsyncThread()
    try:
        # The loop start is gated, so the loop is provably not running yet.
        assert not async_thread._eventloop.is_running()

        # Let the loop reach run_forever() shortly after run_coro starts waiting.
        def release_gate() -> None:
            time.sleep(0.1)
            gate.set()

        releaser = threading.Thread(target=release_gate)
        releaser.start()

        assert async_thread.run_coro(_return(42)) == 42
        releaser.join()
    finally:
        gate.set()
        async_thread.close()


def test_run_coro_raises_after_close() -> None:
    """`run_coro` raises `RuntimeError` once the loop has been closed."""
    async_thread = AsyncThread()
    async_thread.close()

    coro = _return(42)
    with pytest.raises(RuntimeError):
        async_thread.run_coro(coro)
    coro.close()


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


def test_submit_coro_runs_the_coroutine_without_blocking() -> None:
    """`submit_coro` schedules the coroutine on the background loop and returns before it completes."""
    thread = AsyncThread()
    _wait_until_running(thread)

    release = threading.Event()
    finished = threading.Event()

    async def gated() -> None:
        await asyncio.to_thread(release.wait)
        finished.set()

    thread.submit_coro(gated())

    # The call returned while the coroutine is still parked on the gate.
    assert not finished.is_set()

    release.set()
    assert finished.wait(timeout=2)

    thread.close()


def test_submit_coro_logs_a_failing_coroutine(caplog: pytest.LogCaptureFixture) -> None:
    """A coroutine submitted without a caller to propagate to has its failure logged instead of swallowed."""
    thread = AsyncThread()
    _wait_until_running(thread)

    async def boom() -> None:
        raise RuntimeError('boom')

    with caplog.at_level(logging.ERROR, logger='apify.scrapy._async_thread'):
        thread.submit_coro(boom())
        thread.close()

    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(errors) == 1
    assert errors[0].exc_info is not None
    assert str(errors[0].exc_info[1]) == 'boom'


def test_submit_coro_raises_after_close() -> None:
    """`submit_coro` raises `RuntimeError` once the loop has been closed."""
    thread = AsyncThread()
    thread.close()

    coro = _return(42)
    with pytest.raises(RuntimeError):
        thread.submit_coro(coro)
    coro.close()


def test_wait_for_submitted_blocks_until_the_coroutines_finish() -> None:
    """`wait_for_submitted` waits for the fire-and-forget coroutines, so `close` cannot cancel them."""
    thread = AsyncThread()
    _wait_until_running(thread)

    release = threading.Event()
    finished = threading.Event()

    async def gated() -> None:
        await asyncio.to_thread(release.wait)
        finished.set()

    thread.submit_coro(gated())
    release.set()

    thread.wait_for_submitted()

    assert finished.is_set()
    thread.close()


def test_wait_for_submitted_keeps_an_unfinished_coroutine_tracked(caplog: pytest.LogCaptureFixture) -> None:
    """A coroutine that outlasts the timeout stays tracked and is reported, so a later call can wait for it."""
    thread = AsyncThread()
    _wait_until_running(thread)

    release = threading.Event()

    async def gated() -> None:
        await asyncio.to_thread(release.wait)

    thread.submit_coro(gated())

    with caplog.at_level(logging.WARNING, logger='apify.scrapy._async_thread'):
        thread.wait_for_submitted(timeout=timedelta(seconds=0.01))
    assert len(thread._submitted) == 1
    assert [record for record in caplog.records if record.levelno == logging.WARNING]

    release.set()
    thread.wait_for_submitted()
    assert thread._submitted == []

    thread.close()


def test_submit_coro_drops_the_finished_futures() -> None:
    """Only the coroutines still running stay tracked, so a long crawl does not pile up finished futures."""
    thread = AsyncThread()
    _wait_until_running(thread)

    for _ in range(SUBMITTED_PRUNE_THRESHOLD):
        thread.submit_coro(_return(1))

    assert futures.wait(list(thread._submitted), timeout=2).not_done == set()

    # Every tracked coroutine has finished, so this submission drops them instead of growing the list.
    thread.submit_coro(_return(1))
    assert len(thread._submitted) == 1

    thread.close()
