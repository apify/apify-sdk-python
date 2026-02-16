from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Coroutine


def run_scrapy_actor(coro: Coroutine) -> None:
    """Start Twisted's reactor and execute the provided Actor coroutine.

    This function installs Twisted's asyncio-compatible reactor, then initiates it and runs the given asyncio
    coroutine (typically the Actor's main) by converting it to a Deferred. This bridges the asyncio and Twisted
    event loops, enabling the Apify and Scrapy integration to work together.
    """
    from scrapy.utils.reactor import install_reactor  # noqa: PLC0415

    install_reactor('twisted.internet.asyncioreactor.AsyncioSelectorReactor')

    from twisted.internet.defer import Deferred  # noqa: PLC0415
    from twisted.internet.task import react  # noqa: PLC0415

    react(lambda _reactor: Deferred.fromFuture(asyncio.ensure_future(coro)))
