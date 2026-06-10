from __future__ import annotations

import logging
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
