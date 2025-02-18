from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from twisted.internet.defer import Deferred, ensureDeferred
from twisted.internet.task import react

if TYPE_CHECKING:
    from collections.abc import Coroutine


async def _run_coro_as_deferred(coro: Coroutine) -> None:
    """Wrap the given asyncio coroutine in a Task and await its result as a Twisted Deferred."""
    task = asyncio.ensure_future(coro)
    await Deferred.fromFuture(task)


def run_scrapy_actor(coro: Coroutine) -> None:
    """Start Twisted's reactor and execute the provided Actor coroutine.

    This function initiates the Twisted reactor and runs the given asyncio coroutine (typically the
    Actor's main) by converting it to a Deferred. This bridges the asyncio and Twisted event loops,
    enabling the Apify and Scrapy integration to work together.
    """
    react(lambda _: ensureDeferred(_run_coro_as_deferred(coro)))
