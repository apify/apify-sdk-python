from __future__ import annotations

import asyncio
import logging
from concurrent.futures import Future
from datetime import timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest import mock

import pytest
from scrapy import Request, Spider
from scrapy.settings import Settings

from apify import Request as ApifyRequest
from apify.scrapy.scheduler import ApifyScheduler
from apify.storages import RequestQueue

if TYPE_CHECKING:
    from collections.abc import Coroutine


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


class FakeAsyncThread:
    """Stand-in for `AsyncThread` that runs the scheduler's coroutines on a real event loop.

    The scheduler batches the updates of a whole resolution pass into a single coroutine, so a double that
    never runs them would leave these tests asserting on the batching instead of on what reaches the RQ.
    """

    def __init__(self, default_timeout: timedelta | None = None) -> None:
        self.default_timeout = default_timeout
        self.calls: list[str] = []
        """The methods called on this thread, in order, for the tests that care about the ordering."""

    def run_coro(self, coro: Coroutine) -> Any:
        self.calls.append('run_coro')
        return asyncio.run(coro)

    def submit_coro(self, coro: Coroutine) -> Future:
        self.calls.append('submit_coro')
        future: Future = Future()
        try:
            future.set_result(asyncio.run(coro))
        except Exception as exc:
            future.set_exception(exc)
        return future

    def wait_for_submitted(self) -> None:
        self.calls.append('wait_for_submitted')

    def close(self) -> None:
        self.calls.append('close')


def stub_scheduler_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub out the reactor check, the event loop thread and the RQ that `open` reaches for."""
    monkeypatch.setattr('apify.scrapy.scheduler.is_asyncio_reactor_installed', lambda: True)
    monkeypatch.setattr('apify.scrapy.scheduler.AsyncThread', FakeAsyncThread)

    async def open_rq(*_args: Any, **_kwargs: Any) -> Any:
        rq = mock.AsyncMock()
        rq.__class__ = RequestQueue
        return rq

    monkeypatch.setattr(RequestQueue, 'open', open_rq)


@pytest.fixture
def scheduler(monkeypatch: pytest.MonkeyPatch, spider: DummySpider) -> ApifyScheduler:
    """Create a scheduler with its reactor check stubbed out, a fake event loop thread and a mocked RQ."""
    stub_scheduler_dependencies(monkeypatch)

    scheduler = ApifyScheduler()
    scheduler.spider = spider

    rq = mock.AsyncMock()
    rq.__class__ = RequestQueue
    scheduler._rq = rq

    return scheduler


def test_has_pending_requests_reflects_queue_state(scheduler: ApifyScheduler) -> None:
    """`has_pending_requests` is True while the queue is not finished and False once it is."""
    rq = cast('mock.AsyncMock', scheduler._rq)

    rq.is_finished.return_value = False  # the RQ still has work
    assert scheduler.has_pending_requests() is True

    rq.is_finished.return_value = True  # the RQ is drained
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
    rq = cast('mock.AsyncMock', scheduler._rq)
    rq.add_request.return_value = SimpleNamespace(was_already_present=False)

    result = scheduler.enqueue_request(Request(url='https://example.com'))

    assert result is True
    rq.add_request.assert_called_once()


def test_enqueue_request_returns_false_for_duplicate(scheduler: ApifyScheduler) -> None:
    """A request already present in the queue is reported as not newly enqueued (returns False)."""
    rq = cast('mock.AsyncMock', scheduler._rq)
    rq.add_request.return_value = SimpleNamespace(was_already_present=True)

    result = scheduler.enqueue_request(Request(url='https://example.com'))

    assert result is False


def test_next_request_skips_request_that_fails_to_convert(
    scheduler: ApifyScheduler,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A queue entry that fails to reconstruct is skipped and still marked handled, not retried forever."""
    rq = cast('mock.AsyncMock', scheduler._rq)

    # A queue entry whose encoded Scrapy request is malformed; `to_scrapy_request` raises on it.
    malformed_request = ApifyRequest(
        url='https://example.com',
        method='GET',
        unique_key='https://example.com',
        user_data={'scrapy_request': 'this is not a correctly encoded Scrapy request'},
    )

    rq.fetch_next_request.return_value = malformed_request

    with caplog.at_level(logging.WARNING, logger='apify.scrapy.scheduler'):
        result = scheduler.next_request()

    # The malformed request is skipped instead of crashing the whole run.
    assert result is None
    assert 'skipping it' in caplog.text

    # Even though conversion failed, the unrecoverable entry is still marked as handled (consumed), so
    # the queue does not keep handing it back forever.
    rq.mark_request_as_handled.assert_called_once_with(malformed_request)


def test_next_request_returns_converted_request(scheduler: ApifyScheduler) -> None:
    """A valid RQ entry is reconstructed into a Scrapy request and left unhandled until Scrapy is done."""
    rq = cast('mock.AsyncMock', scheduler._rq)

    apify_request = ApifyRequest(
        url='https://example.com',
        method='GET',
        unique_key='https://example.com',
        user_data={},
    )
    rq.fetch_next_request.return_value = apify_request

    result = scheduler.next_request()

    assert isinstance(result, Request)
    assert result.url == apify_request.url
    rq.mark_request_as_handled.assert_not_called()


def test_next_request_returns_none_when_queue_empty(scheduler: ApifyScheduler) -> None:
    """An empty queue makes `next_request` return None and skip marking anything as handled."""
    rq = cast('mock.AsyncMock', scheduler._rq)
    rq.fetch_next_request.return_value = None

    result = scheduler.next_request()

    assert result is None
    rq.mark_request_as_handled.assert_not_called()


def test_next_request_logs_exception_before_propagating(
    scheduler: ApifyScheduler,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failure in the coroutine run is logged with its traceback via `logger.exception` before propagating."""
    rq = cast('mock.AsyncMock', scheduler._rq)
    rq.fetch_next_request.side_effect = RuntimeError('boom')

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


APIFY_REQUESTS = [
    ApifyRequest(
        url=f'https://example.com/{index}',
        method='GET',
        unique_key=f'https://example.com/{index}',
        user_data={},
    )
    for index in range(4)
]


def hand_out(scheduler: ApifyScheduler, count: int) -> list[Request]:
    """Fetch `count` requests, keeping each busy in Scrapy so it is not resolved as it is handed over.

    Returns the Scrapy requests, and leaves the crawler stub reporting all of them as busy in the downloader.
    """
    rq = cast('mock.AsyncMock', scheduler._rq)
    rq.fetch_next_request.side_effect = APIFY_REQUESTS[:count]

    busy: set[Request] = set()
    scheduler._crawler = fake_crawler(downloader_busy=busy)

    for _ in range(count):
        busy.add(cast('Request', scheduler.next_request()))

    rq.fetch_next_request.side_effect = None
    rq.fetch_next_request.return_value = None

    return list(busy)


def test_has_pending_requests_marks_finished_requests_as_handled(scheduler: ApifyScheduler) -> None:
    """Requests Scrapy has finished with are marked as handled once it goes idle and asks about pending work."""
    rq = cast('mock.AsyncMock', scheduler._rq)

    rq.fetch_next_request.return_value = APIFY_REQUESTS[0]
    scheduler.next_request()
    rq.mark_request_as_handled.assert_not_called()

    # Scrapy asks about pending work only once its downloader and its scraper are both idle.
    scheduler._crawler = fake_crawler(scraper_busy=set())
    rq.is_finished.return_value = True
    assert scheduler.has_pending_requests() is False

    rq.mark_request_as_handled.assert_called_once_with(APIFY_REQUESTS[0])


def test_next_request_marks_finished_requests_without_blocking(scheduler: ApifyScheduler) -> None:
    """On the crawl's hot path a finished request is marked as handled without blocking the reactor on it."""
    rq = cast('mock.AsyncMock', scheduler._rq)
    async_thread = cast('FakeAsyncThread', scheduler._async_thread)

    (scrapy_request,) = hand_out(scheduler, 1)

    # Scrapy is still downloading the request, so it stays unresolved.
    scheduler._crawler = fake_crawler(downloader_busy={scrapy_request})
    assert scheduler.next_request() is None
    rq.mark_request_as_handled.assert_not_called()

    # Scrapy is done with it, so it is resolved off the reactor thread instead of blocking on the round trip.
    scheduler._crawler = fake_crawler(scraper_busy=set())
    async_thread.calls.clear()
    assert scheduler.next_request() is None

    rq.mark_request_as_handled.assert_called_once_with(APIFY_REQUESTS[0])
    assert 'submit_coro' in async_thread.calls


def test_has_pending_requests_waits_for_the_non_blocking_updates(scheduler: ApifyScheduler) -> None:
    """The RQ is asked whether it is finished only after the updates fired off on the hot path have landed."""
    rq = cast('mock.AsyncMock', scheduler._rq)
    async_thread = cast('FakeAsyncThread', scheduler._async_thread)
    scheduler._crawler = fake_crawler()

    rq.is_finished.return_value = True
    assert scheduler.has_pending_requests() is False

    # The RQ answers from its own bookkeeping, which a pending update has not reached yet.
    assert async_thread.calls == ['wait_for_submitted', 'run_coro']


@pytest.mark.parametrize(
    'busy_kwarg',
    [
        pytest.param('downloader_busy', id='busy in the downloader'),
        pytest.param('scraper_busy', id='busy in the scraper slot'),
    ],
)
def test_close_reclaims_requests_scrapy_never_finished(scheduler: ApifyScheduler, busy_kwarg: str) -> None:
    """Requests still being processed when the scheduler closes go back to the RQ instead of being lost."""
    rq = cast('mock.AsyncMock', scheduler._rq)

    (scrapy_request,) = hand_out(scheduler, 1)

    # Scrapy is still working on the request when the run is interrupted.
    scheduler._crawler = fake_crawler(**{busy_kwarg: {scrapy_request}})

    scheduler.close('shutdown')

    rq.reclaim_request.assert_called_once_with(APIFY_REQUESTS[0])
    rq.mark_request_as_handled.assert_not_called()


def test_close_marks_the_requests_scrapy_finished_as_handled(scheduler: ApifyScheduler) -> None:
    """Requests Scrapy drained before the shutdown are marked as handled rather than reclaimed."""
    rq = cast('mock.AsyncMock', scheduler._rq)

    hand_out(scheduler, 1)

    # Scrapy drains its downloader and its scraper before the scheduler is closed.
    scheduler._crawler = fake_crawler(scraper_busy=set())

    scheduler.close('finished')

    rq.mark_request_as_handled.assert_called_once_with(APIFY_REQUESTS[0])
    rq.reclaim_request.assert_not_called()


def test_close_reclaims_the_other_requests_after_a_failed_reclaim(
    scheduler: ApifyScheduler,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One failing reclaim does not stop the other in-flight requests from going back to the RQ."""
    rq = cast('mock.AsyncMock', scheduler._rq)

    hand_out(scheduler, 2)
    rq.reclaim_request.side_effect = [RuntimeError('boom'), None]

    with caplog.at_level(logging.ERROR, logger='apify.scrapy.scheduler'):
        scheduler.close('shutdown')

    assert rq.reclaim_request.call_count == 2
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(errors) == 1


def test_close_reaches_the_rq_in_one_round_trip_per_operation(scheduler: ApifyScheduler) -> None:
    """Marks and reclaims each travel together, as a migration may not leave room for one round trip each."""
    rq = cast('mock.AsyncMock', scheduler._rq)
    async_thread = cast('FakeAsyncThread', scheduler._async_thread)

    handed_out = hand_out(scheduler, 4)

    # Scrapy finished half of the requests and is still working on the rest when the run is interrupted.
    scheduler._crawler = fake_crawler(downloader_busy=set(handed_out[2:]))

    async_thread.calls.clear()
    scheduler.close('shutdown')

    assert rq.mark_request_as_handled.await_count == 2
    assert rq.reclaim_request.await_count == 2
    assert async_thread.calls.count('run_coro') == 2


def test_close_waits_for_the_non_blocking_updates(scheduler: ApifyScheduler) -> None:
    """The event loop is not torn down before the updates fired off on the hot path have landed."""
    async_thread = cast('FakeAsyncThread', scheduler._async_thread)

    scheduler.close('finished')

    assert async_thread.calls.index('wait_for_submitted') < async_thread.calls.index('close')


def test_a_failed_mark_keeps_the_request_tracked(
    scheduler: ApifyScheduler,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A request whose mark-as-handled fails stays tracked, so the next resolution retries it."""
    rq = cast('mock.AsyncMock', scheduler._rq)

    hand_out(scheduler, 1)

    scheduler._crawler = fake_crawler()
    # The mark fails, then the RQ reports itself unfinished because the request is still in progress.
    rq.mark_request_as_handled.side_effect = RuntimeError('boom')
    rq.is_finished.return_value = False

    with caplog.at_level(logging.ERROR, logger='apify.scrapy.scheduler'):
        assert scheduler.has_pending_requests() is True

    assert scheduler._requests_in_flight
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(errors) == 1


def test_a_mark_that_fails_after_being_fired_off_is_retried(
    scheduler: ApifyScheduler,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A hot-path mark that fails on its way to the RQ is retried, instead of leaving the request in progress."""
    rq = cast('mock.AsyncMock', scheduler._rq)

    hand_out(scheduler, 1)

    # Scrapy is done with the request, so the hot path fires the mark off - and it fails out of sight.
    scheduler._crawler = fake_crawler()
    rq.mark_request_as_handled.side_effect = RuntimeError('boom')
    assert scheduler.next_request() is None

    # The failure only surfaces on the next pass, which picks the request back up and marks it again.
    rq.mark_request_as_handled.side_effect = None
    rq.is_finished.return_value = True

    with caplog.at_level(logging.ERROR, logger='apify.scrapy.scheduler'):
        assert scheduler.has_pending_requests() is False

    assert rq.mark_request_as_handled.await_count == 2
    assert not scheduler._requests_in_flight
    assert not scheduler._pending_marks


def test_open_warns_when_built_without_a_crawler(
    monkeypatch: pytest.MonkeyPatch,
    spider: DummySpider,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Without a crawler the scheduler cannot see what Scrapy holds, and that must not pass silently."""
    stub_scheduler_dependencies(monkeypatch)

    with caplog.at_level(logging.WARNING, logger='apify.scrapy.scheduler'):
        ApifyScheduler().open(spider)

    assert 'without a crawler' in caplog.text


def test_open_is_quiet_with_a_crawler(
    monkeypatch: pytest.MonkeyPatch,
    spider: DummySpider,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A scheduler that can read the engine internals it relies on opens without complaining."""
    stub_scheduler_dependencies(monkeypatch)

    with caplog.at_level(logging.WARNING, logger='apify.scrapy.scheduler'):
        ApifyScheduler(crawler=fake_crawler(scraper_busy=set())).open(spider)

    assert not [record for record in caplog.records if record.name == 'apify.scrapy.scheduler']


def test_open_fails_loudly_when_the_scrapy_engine_internals_move(
    monkeypatch: pytest.MonkeyPatch,
    spider: DummySpider,
) -> None:
    """A Scrapy release that moves the engine internals has to break at open, not silently mid-crawl."""
    stub_scheduler_dependencies(monkeypatch)
    crawler = SimpleNamespace(engine=SimpleNamespace(downloader=SimpleNamespace(), scraper=SimpleNamespace()))

    with pytest.raises(RuntimeError, match='engine internals'):
        ApifyScheduler(crawler=cast('Any', crawler)).open(spider)


def test_from_crawler_keeps_the_crawler(monkeypatch: pytest.MonkeyPatch) -> None:
    """`from_crawler` keeps the crawler, which is how the scheduler learns what Scrapy is still working on."""
    monkeypatch.setattr('apify.scrapy.scheduler.is_asyncio_reactor_installed', lambda: True)
    monkeypatch.setattr('apify.scrapy.scheduler.AsyncThread', mock.MagicMock())

    crawler = SimpleNamespace(settings=Settings())
    scheduler = ApifyScheduler.from_crawler(cast('Any', crawler))

    assert scheduler._crawler is crawler
