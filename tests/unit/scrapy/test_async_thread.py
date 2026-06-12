from __future__ import annotations

import threading
import time

import pytest

from apify.scrapy._async_thread import AsyncThread


async def _return(value: int) -> int:
    return value


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
