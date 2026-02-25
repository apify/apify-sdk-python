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
    from twisted.internet.error import ReactorAlreadyInstalledError  # noqa: PLC0415

    try:
        install_reactor('twisted.internet.asyncioreactor.AsyncioSelectorReactor')
    except ReactorAlreadyInstalledError:
        from twisted.internet import reactor as installed_reactor  # noqa: PLC0415

        reactor_cls = type(installed_reactor)
        if (
            reactor_cls.__module__ != 'twisted.internet.asyncioreactor'
            or reactor_cls.__name__ != 'AsyncioSelectorReactor'
        ):
            raise RuntimeError(
                'A Twisted reactor is already installed and it is not AsyncioSelectorReactor. '
                'Make sure that run_scrapy_actor() is called before importing any Scrapy or Twisted '
                'modules that install a reactor (e.g. scrapy.crawler).'
            ) from None

    from twisted.internet.defer import Deferred  # noqa: PLC0415
    from twisted.internet.task import react  # noqa: PLC0415

    react(lambda _reactor: Deferred.fromFuture(asyncio.ensure_future(coro)))
