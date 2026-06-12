from __future__ import annotations

import logging
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest import mock

import pytest
from scrapy import Request, Spider
from scrapy.settings import Settings

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


def test_has_pending_requests_reflects_queue_state(scheduler: ApifyScheduler) -> None:
    """`has_pending_requests` is True while the queue is not finished and False once it is."""
    async_thread = cast('mock.MagicMock', scheduler._async_thread)

    async_thread.run_coro.return_value = False  # the queue still has work
    assert scheduler.has_pending_requests() is True

    async_thread.run_coro.return_value = True  # the queue is drained
    assert scheduler.has_pending_requests() is False


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


def test_next_request_returns_none_when_queue_empty(scheduler: ApifyScheduler) -> None:
    """An empty queue makes `next_request` return None and skip marking anything as handled."""
    rq = cast('mock.MagicMock', scheduler._rq)
    async_thread = cast('mock.MagicMock', scheduler._async_thread)
    async_thread.run_coro.return_value = None

    result = scheduler.next_request()

    assert result is None
    rq.mark_request_as_handled.assert_not_called()


def test_next_request_does_not_print_traceback_to_stderr(
    scheduler: ApifyScheduler,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failure propagates as-is, without `traceback.print_exc()` printing a second copy past the log formatter."""
    async_thread = cast('mock.MagicMock', scheduler._async_thread)
    async_thread.run_coro.side_effect = RuntimeError('boom')

    with pytest.raises(RuntimeError, match='boom'):
        scheduler.next_request()

    assert capsys.readouterr().err == ''


def test_from_crawler_reads_async_thread_timeout_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    """`from_crawler` wires the `APIFY_ASYNC_THREAD_TIMEOUT_SECS` setting into the async thread's timeout."""
    monkeypatch.setattr('apify.scrapy.scheduler.is_asyncio_reactor_installed', lambda: True)

    captured: dict[str, Any] = {}

    class _RecordingAsyncThread:
        def __init__(self, default_timeout: timedelta | None = None) -> None:
            captured['default_timeout'] = default_timeout

    monkeypatch.setattr('apify.scrapy.scheduler.AsyncThread', _RecordingAsyncThread)

    crawler = SimpleNamespace(settings=Settings({'APIFY_ASYNC_THREAD_TIMEOUT_SECS': 123}))
    ApifyScheduler.from_crawler(cast('Any', crawler))

    assert captured['default_timeout'] == timedelta(seconds=123)
