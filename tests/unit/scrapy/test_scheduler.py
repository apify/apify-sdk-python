from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import cast
from unittest import mock

import pytest
from scrapy import Request, Spider

from apify import Request as ApifyRequest
from apify.scrapy.scheduler import ApifyScheduler
from apify.storages import RequestQueue


class DummySpider(Spider):
    name = 'dummy_spider'


@pytest.fixture
def spider() -> DummySpider:
    """Fixture to create a "dummy" Scrapy spider."""
    return DummySpider()


@pytest.fixture
def scheduler(monkeypatch: pytest.MonkeyPatch, spider: DummySpider) -> ApifyScheduler:
    """Create a scheduler with its reactor check and async thread stubbed out."""
    monkeypatch.setattr('apify.scrapy.scheduler.is_asyncio_reactor_installed', lambda: True)
    monkeypatch.setattr('apify.scrapy.scheduler.AsyncThread', mock.MagicMock())

    scheduler = ApifyScheduler()
    scheduler.spider = spider

    rq = mock.MagicMock()
    rq.__class__ = RequestQueue
    scheduler._rq = rq

    return scheduler


def test_enqueue_request_skips_non_serializable_request(
    scheduler: ApifyScheduler,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A request that cannot be converted (non-serializable meta) is not enqueued: returns False and logs an error."""
    rq = cast('mock.MagicMock', scheduler._rq)

    # A set in `meta` is not JSON-serializable, so `to_apify_request` returns None.
    scrapy_request = Request(url='https://example.com', meta={'tags': {'a', 'b'}})

    with caplog.at_level(logging.ERROR, logger='apify.scrapy.scheduler'):
        result = scheduler.enqueue_request(scrapy_request)

    assert result is False
    assert 'could not be converted' in caplog.text
    rq.add_request.assert_not_called()


def test_enqueue_request_enqueues_converted_request(scheduler: ApifyScheduler) -> None:
    """A convertible request is enqueued and reported as newly added when the queue had not seen it."""
    rq = cast('mock.MagicMock', scheduler._rq)
    async_thread = cast('mock.MagicMock', scheduler._async_thread)
    async_thread.run_coro.return_value = SimpleNamespace(was_already_present=False)

    result = scheduler.enqueue_request(Request(url='https://example.com'))

    assert result is True
    rq.add_request.assert_called_once()


def test_enqueue_request_returns_false_for_duplicate(scheduler: ApifyScheduler) -> None:
    """A request already present in the queue is reported as not newly enqueued (returns False)."""
    async_thread = cast('mock.MagicMock', scheduler._async_thread)
    async_thread.run_coro.return_value = SimpleNamespace(was_already_present=True)

    result = scheduler.enqueue_request(Request(url='https://example.com'))

    assert result is False


def test_next_request_skips_request_that_fails_to_convert(
    scheduler: ApifyScheduler,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A queue entry that fails to reconstruct is skipped and still marked handled, not retried forever."""
    rq = cast('mock.MagicMock', scheduler._rq)
    async_thread = cast('mock.MagicMock', scheduler._async_thread)

    # A queue entry whose encoded Scrapy request is malformed; `to_scrapy_request` raises on it.
    malformed_request = ApifyRequest(
        url='https://example.com',
        method='GET',
        unique_key='https://example.com',
        user_data={'scrapy_request': 'this is not a correctly encoded Scrapy request'},
    )

    # `run_coro` is called for `fetch_next_request`, then for `mark_request_as_handled`.
    async_thread.run_coro.side_effect = [malformed_request, None]

    with caplog.at_level(logging.ERROR, logger='apify.scrapy.scheduler'):
        result = scheduler.next_request()

    # The malformed request is skipped instead of crashing the whole run.
    assert result is None
    assert 'skipping it' in caplog.text

    # Even though conversion failed, the unrecoverable entry is still marked as handled (consumed), so
    # the queue does not keep handing it back forever.
    rq.mark_request_as_handled.assert_called_once_with(malformed_request)


def test_next_request_returns_converted_request(scheduler: ApifyScheduler) -> None:
    """A valid queue entry is reconstructed into a Scrapy request and marked handled."""
    rq = cast('mock.MagicMock', scheduler._rq)
    async_thread = cast('mock.MagicMock', scheduler._async_thread)

    apify_request = ApifyRequest(
        url='https://example.com',
        method='GET',
        unique_key='https://example.com',
        user_data={},
    )
    async_thread.run_coro.side_effect = [apify_request, None]

    result = scheduler.next_request()

    assert isinstance(result, Request)
    assert result.url == apify_request.url
    rq.mark_request_as_handled.assert_called_once_with(apify_request)
