from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest import mock

from scrapy import signals
from scrapy.signalmanager import SignalManager

from apify import Actor, Event, EventAbortingData
from apify.scrapy._warnings import logger_once
from apify.scrapy.extensions import ApifyGracefulStopExtension

if TYPE_CHECKING:
    import pytest


def fake_crawler() -> Any:
    """Build a crawler stub with a real signal manager and a `stop_async` that records being awaited."""
    return SimpleNamespace(signals=SignalManager(), stop_async=mock.AsyncMock())


def test_the_abort_listener_lives_as_long_as_the_spider(monkeypatch: pytest.MonkeyPatch) -> None:
    """The abort listener is registered with the Actor when the spider opens and unregistered when it closes."""
    actor = mock.Mock()
    monkeypatch.setattr('apify.scrapy.extensions._graceful_stop.Actor', actor)
    crawler = fake_crawler()
    extension = ApifyGracefulStopExtension.from_crawler(crawler)

    crawler.signals.send_catch_log(signal=signals.spider_opened, spider=None)
    actor.on.assert_called_once_with(Event.ABORTING, extension._on_aborting)
    actor.off.assert_not_called()

    crawler.signals.send_catch_log(signal=signals.spider_closed, spider=None, reason='finished')
    actor.off.assert_called_once_with(Event.ABORTING, extension._on_aborting)


async def test_aborting_stops_the_crawler_gracefully() -> None:
    """When the run is aborted, the crawler is stopped gracefully, so the requests in flight can finish."""
    crawler = fake_crawler()
    extension = ApifyGracefulStopExtension.from_crawler(crawler)

    await extension._on_aborting()

    crawler.stop_async.assert_awaited_once_with()


async def test_the_actor_abort_event_reaches_the_extension() -> None:
    """The abort event emitted by an initialized Actor stops the crawler, and no longer does once the spider closed."""
    crawler = fake_crawler()
    extension = ApifyGracefulStopExtension.from_crawler(crawler)

    async with Actor:
        extension.spider_opened()
        Actor.event_manager.emit(event=Event.ABORTING, event_data=EventAbortingData())
        await Actor.event_manager.wait_for_all_listeners_to_complete()
        crawler.stop_async.assert_awaited_once_with()

        extension.spider_closed()
        Actor.event_manager.emit(event=Event.ABORTING, event_data=EventAbortingData())
        await Actor.event_manager.wait_for_all_listeners_to_complete()
        crawler.stop_async.assert_awaited_once_with()


def test_spider_opened_warns_when_the_actor_is_not_initialized(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Without an initialized Actor there is nothing to register the abort listener with, and that is said."""
    monkeypatch.setattr(logger_once, '_seen', set())
    extension = ApifyGracefulStopExtension.from_crawler(fake_crawler())

    with caplog.at_level(logging.WARNING, logger='apify.scrapy._warnings'):
        extension.spider_opened()
    extension.spider_closed()

    assert 'Actor is not initialized' in caplog.text
