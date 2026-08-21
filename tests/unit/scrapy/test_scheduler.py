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


def fake_crawler(
    *,
    downloader_busy: set[Request] | None = None,
    scraper_busy: set[Request] | None = None,
) -> Any:
    """Build a crawler stub reporting the given requests as busy; without `scraper_busy` its scraper slot is None."""
    scraper_slot = SimpleNamespace(active=scraper_busy) if scraper_busy is not None else None
    engine = SimpleNamespace(
        downloader=SimpleNamespace(active=downloader_busy if downloader_busy is not None else set()),
        scraper=SimpleNamespace(slot=scraper_slot),
    )
    return SimpleNamespace(engine=engine)


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
    """A request that cannot be converted (non-serializable meta) is not enqueued: returns False and logs a warning."""
    rq = cast('mock.MagicMock', scheduler._rq)

    # A set in `meta` is not JSON-serializable, so `to_apify_request` returns None.
    scrapy_request = Request(url='https://example.com', meta={'tags': {'a', 'b'}})

    with caplog.at_level(logging.WARNING, logger='apify.scrapy.scheduler'):
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

    with caplog.at_level(logging.WARNING, logger='apify.scrapy.scheduler'):
        result = scheduler.next_request()

    # The malformed request is skipped instead of crashing the whole run.
    assert result is None
    assert 'skipping it' in caplog.text

    # Even though conversion failed, the unrecoverable entry is still marked as handled (consumed), so
    # the queue does not keep handing it back forever.
    rq.mark_request_as_handled.assert_called_once_with(malformed_request)


def test_next_request_returns_converted_request(scheduler: ApifyScheduler) -> None:
    """A valid queue entry is reconstructed into a Scrapy request and left unhandled until Scrapy is done."""
    rq = cast('mock.MagicMock', scheduler._rq)
    async_thread = cast('mock.MagicMock', scheduler._async_thread)

    apify_request = ApifyRequest(
        url='https://example.com',
        method='GET',
        unique_key='https://example.com',
        user_data={},
    )
    async_thread.run_coro.return_value = apify_request

    result = scheduler.next_request()

    assert isinstance(result, Request)
    assert result.url == apify_request.url
    rq.mark_request_as_handled.assert_not_called()


def test_next_request_returns_none_when_queue_empty(scheduler: ApifyScheduler) -> None:
    """An empty queue makes `next_request` return None and skip marking anything as handled."""
    rq = cast('mock.MagicMock', scheduler._rq)
    async_thread = cast('mock.MagicMock', scheduler._async_thread)
    async_thread.run_coro.return_value = None

    result = scheduler.next_request()

    assert result is None
    rq.mark_request_as_handled.assert_not_called()


def test_next_request_logs_exception_before_propagating(
    scheduler: ApifyScheduler,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failure in the coroutine run is logged with its traceback via `logger.exception` before propagating."""
    async_thread = cast('mock.MagicMock', scheduler._async_thread)
    async_thread.run_coro.side_effect = RuntimeError('boom')

    with caplog.at_level(logging.ERROR, logger='apify.scrapy.scheduler'), pytest.raises(RuntimeError, match='boom'):
        scheduler.next_request()

    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(errors) == 1
    (error,) = errors
    assert error.exc_info is not None
    assert isinstance(error.exc_info[1], RuntimeError)
    assert str(error.exc_info[1]) == 'boom'


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


def test_has_pending_requests_marks_finished_requests_as_handled(scheduler: ApifyScheduler) -> None:
    """Requests Scrapy has finished with are marked as handled once it goes idle and asks about pending work."""
    rq = cast('mock.MagicMock', scheduler._rq)
    async_thread = cast('mock.MagicMock', scheduler._async_thread)

    apify_request = ApifyRequest(
        url='https://example.com',
        method='GET',
        unique_key='https://example.com',
        user_data={},
    )
    async_thread.run_coro.return_value = apify_request
    scheduler.next_request()
    rq.mark_request_as_handled.assert_not_called()

    # Scrapy asks about pending work only once its downloader and its scraper are both idle.
    scheduler._crawler = fake_crawler(scraper_busy=set())
    async_thread.run_coro.return_value = True  # the queue reports itself finished
    assert scheduler.has_pending_requests() is False

    rq.mark_request_as_handled.assert_called_once_with(apify_request)


def test_next_request_marks_finished_requests_without_blocking(scheduler: ApifyScheduler) -> None:
    """On the crawl's hot path a finished request is marked as handled without blocking the reactor on it."""
    rq = cast('mock.MagicMock', scheduler._rq)
    async_thread = cast('mock.MagicMock', scheduler._async_thread)

    apify_request = ApifyRequest(
        url='https://example.com',
        method='GET',
        unique_key='https://example.com',
        user_data={},
    )
    async_thread.run_coro.return_value = apify_request
    scrapy_request = scheduler.next_request()

    # The queue is drained from here on, so no further request is handed out.
    async_thread.run_coro.return_value = None

    # Scrapy is still downloading the request, so it stays unresolved.
    scheduler._crawler = fake_crawler(downloader_busy={cast('Request', scrapy_request)})
    assert scheduler.next_request() is None
    async_thread.submit_coro.assert_not_called()

    # Scrapy is done with it, so it is resolved off the reactor thread instead of blocking on the round trip.
    scheduler._crawler = fake_crawler(scraper_busy=set())
    assert scheduler.next_request() is None

    rq.mark_request_as_handled.assert_called_once_with(apify_request)
    async_thread.submit_coro.assert_called_once_with(rq.mark_request_as_handled.return_value)


def test_has_pending_requests_waits_for_the_non_blocking_updates(scheduler: ApifyScheduler) -> None:
    """The queue is asked whether it is finished only after the updates fired off on the hot path have landed."""
    async_thread = cast('mock.MagicMock', scheduler._async_thread)
    scheduler._crawler = fake_crawler()

    async_thread.run_coro.return_value = True  # the queue reports itself finished
    assert scheduler.has_pending_requests() is False

    # The queue answers from its own bookkeeping, which a pending update has not reached yet.
    assert async_thread.mock_calls == [
        mock.call.wait_for_submitted(),
        mock.call.run_coro(cast('mock.MagicMock', scheduler._rq).is_finished()),
    ]


@pytest.mark.parametrize(
    'busy_kwarg',
    [
        pytest.param('downloader_busy', id='busy in the downloader'),
        pytest.param('scraper_busy', id='busy in the scraper slot'),
    ],
)
def test_close_reclaims_requests_scrapy_never_finished(scheduler: ApifyScheduler, busy_kwarg: str) -> None:
    """Requests still being processed when the scheduler closes go back to the queue instead of being lost."""
    rq = cast('mock.MagicMock', scheduler._rq)
    async_thread = cast('mock.MagicMock', scheduler._async_thread)

    apify_request = ApifyRequest(
        url='https://example.com',
        method='GET',
        unique_key='https://example.com',
        user_data={},
    )
    async_thread.run_coro.return_value = apify_request
    scrapy_request = scheduler.next_request()

    # Scrapy is still working on the request when the run is interrupted.
    scheduler._crawler = fake_crawler(**{busy_kwarg: {cast('Request', scrapy_request)}})

    scheduler.close('shutdown')

    rq.reclaim_request.assert_called_once_with(apify_request)
    rq.mark_request_as_handled.assert_not_called()


def test_close_marks_the_requests_scrapy_finished_as_handled(scheduler: ApifyScheduler) -> None:
    """Requests Scrapy drained before the shutdown are marked as handled rather than reclaimed."""
    rq = cast('mock.MagicMock', scheduler._rq)
    async_thread = cast('mock.MagicMock', scheduler._async_thread)

    apify_request = ApifyRequest(
        url='https://example.com',
        method='GET',
        unique_key='https://example.com',
        user_data={},
    )
    async_thread.run_coro.return_value = apify_request
    scheduler.next_request()

    # Scrapy drains its downloader and its scraper before the scheduler is closed.
    scheduler._crawler = fake_crawler(scraper_busy=set())

    scheduler.close('finished')

    rq.mark_request_as_handled.assert_called_once_with(apify_request)
    rq.reclaim_request.assert_not_called()


def test_close_reclaims_the_other_requests_after_a_failed_reclaim(
    scheduler: ApifyScheduler,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One failing reclaim does not stop the other in-flight requests from going back to the queue."""
    rq = cast('mock.MagicMock', scheduler._rq)
    async_thread = cast('mock.MagicMock', scheduler._async_thread)

    apify_requests = [
        ApifyRequest(
            url=f'https://example.com/{index}',
            method='GET',
            unique_key=f'https://example.com/{index}',
            user_data={},
        )
        for index in range(2)
    ]

    # The crawler stub keeps a reference to this set, so both requests stay busy as they are handed out.
    busy: set[Request] = set()
    scheduler._crawler = fake_crawler(downloader_busy=busy)

    async_thread.run_coro.side_effect = apify_requests
    for _ in apify_requests:
        busy.add(cast('Request', scheduler.next_request()))

    async_thread.run_coro.side_effect = [RuntimeError('boom'), None]

    with caplog.at_level(logging.ERROR, logger='apify.scrapy.scheduler'):
        scheduler.close('shutdown')

    assert rq.reclaim_request.call_count == len(apify_requests)
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(errors) == 1


def test_close_waits_for_the_non_blocking_updates(scheduler: ApifyScheduler) -> None:
    """The event loop is not torn down before the updates fired off on the hot path have landed."""
    async_thread = cast('mock.MagicMock', scheduler._async_thread)

    scheduler.close('finished')

    calls = async_thread.mock_calls
    assert calls.index(mock.call.wait_for_submitted()) < calls.index(mock.call.close())


def test_a_failed_mark_keeps_the_request_tracked(
    scheduler: ApifyScheduler,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A request whose mark-as-handled fails stays tracked, so the next resolution retries it."""
    async_thread = cast('mock.MagicMock', scheduler._async_thread)

    apify_request = ApifyRequest(
        url='https://example.com',
        method='GET',
        unique_key='https://example.com',
        user_data={},
    )
    async_thread.run_coro.return_value = apify_request
    scheduler.next_request()

    scheduler._crawler = fake_crawler()
    # The mark fails, then the queue reports itself unfinished because the request is still in progress.
    async_thread.run_coro.side_effect = [RuntimeError('boom'), False]

    with caplog.at_level(logging.ERROR, logger='apify.scrapy.scheduler'):
        assert scheduler.has_pending_requests() is True

    assert scheduler._requests_in_flight
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(errors) == 1


def test_from_crawler_keeps_the_crawler(monkeypatch: pytest.MonkeyPatch) -> None:
    """`from_crawler` keeps the crawler, which is how the scheduler learns what Scrapy is still working on."""
    monkeypatch.setattr('apify.scrapy.scheduler.is_asyncio_reactor_installed', lambda: True)
    monkeypatch.setattr('apify.scrapy.scheduler.AsyncThread', mock.MagicMock())

    crawler = SimpleNamespace(settings=Settings())
    scheduler = ApifyScheduler.from_crawler(cast('Any', crawler))

    assert scheduler._crawler is crawler
