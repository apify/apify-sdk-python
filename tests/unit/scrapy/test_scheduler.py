from __future__ import annotations

import asyncio
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest
from scrapy import Request, Spider
from scrapy.crawler import Crawler
from scrapy.settings import Settings

from apify import Event, EventMigratingData
from apify import Request as ApifyRequest
from apify.scrapy._async_thread import AsyncThread
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
) -> mock.Mock:
    """Build a crawler double reporting the given requests as busy; without `scraper_busy` its scraper slot is None."""
    scraper_slot = SimpleNamespace(active=scraper_busy) if scraper_busy is not None else None
    crawler = mock.Mock(spec=Crawler)
    crawler.settings = Settings()
    crawler.engine = SimpleNamespace(
        downloader=SimpleNamespace(active=downloader_busy if downloader_busy is not None else set()),
        scraper=SimpleNamespace(slot=scraper_slot),
    )
    return crawler


def fake_rq() -> mock.AsyncMock:
    """Build an RQ double that passes the scheduler's `isinstance` check."""
    rq = mock.AsyncMock()
    rq.__class__ = RequestQueue
    return rq


def fake_async_thread(default_timeout: timedelta | None = None) -> mock.Mock:  # noqa: ARG001
    """Build an `AsyncThread` double that runs the scheduler's coroutines to completion on a real event loop.

    The scheduler batches the updates of a whole resolution pass into a single coroutine, so a double that
    never runs them would leave these tests asserting on the batching instead of on what reaches the RQ. Like
    the real thread, the coroutines run on a worker thread, so the double also works from within an async test.
    """
    executor = ThreadPoolExecutor(max_workers=1)

    def run_coro(coro: Coroutine, timeout: Any = 'default') -> Any:  # noqa: ARG001
        return executor.submit(asyncio.run, coro).result()

    def submit_coro(coro: Coroutine) -> Future:
        future: Future = Future()
        try:
            future.set_result(run_coro(coro))
        except Exception as exc:
            future.set_exception(exc)
        return future

    async_thread = mock.Mock(spec=AsyncThread)
    async_thread.run_coro.side_effect = run_coro
    async_thread.submit_coro.side_effect = submit_coro
    return async_thread


def called_methods(async_thread: mock.Mock) -> list[str]:
    """Name the methods called on an `AsyncThread` double, in order, for the tests that care about the ordering."""
    return [name for name, _args, _kwargs in async_thread.method_calls]


def stub_scheduler_dependencies(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """Stub out the reactor check, the event loop thread, the Actor and the RQ that `open` reaches for.

    Returns the Actor double, for the tests that care about what the scheduler registers with it.
    """
    actor = mock.Mock()
    monkeypatch.setattr('apify.scrapy.scheduler.is_asyncio_reactor_installed', lambda: True)
    monkeypatch.setattr('apify.scrapy.scheduler.AsyncThread', mock.Mock(side_effect=fake_async_thread))
    monkeypatch.setattr('apify.scrapy.scheduler.Actor', actor)

    async def open_rq(*_args: Any, **_kwargs: Any) -> RequestQueue:
        return fake_rq()

    monkeypatch.setattr(RequestQueue, 'open', open_rq)

    return actor


@pytest.fixture
def rq() -> mock.AsyncMock:
    """The RQ double the `scheduler` fixture talks to."""
    return fake_rq()


@pytest.fixture
def async_thread() -> mock.Mock:
    """The `AsyncThread` double the `scheduler` fixture runs its coroutines on."""
    return fake_async_thread()


@pytest.fixture
def scheduler(
    monkeypatch: pytest.MonkeyPatch,
    spider: DummySpider,
    rq: mock.AsyncMock,
    async_thread: mock.Mock,
) -> ApifyScheduler:
    """Create a scheduler with its reactor check stubbed out, a fake event loop thread and a mocked RQ."""
    stub_scheduler_dependencies(monkeypatch)
    monkeypatch.setattr('apify.scrapy.scheduler.AsyncThread', mock.Mock(return_value=async_thread))

    scheduler = ApifyScheduler()
    scheduler.spider = spider
    scheduler._rq = rq

    return scheduler


def test_has_pending_requests_reflects_queue_state(scheduler: ApifyScheduler, rq: mock.AsyncMock) -> None:
    """`has_pending_requests` is True while the queue is not finished and False once it is."""
    rq.is_finished.return_value = False  # the RQ still has work
    assert scheduler.has_pending_requests() is True

    rq.is_finished.return_value = True  # the RQ is drained
    assert scheduler.has_pending_requests() is False


def test_enqueue_request_skips_non_serializable_request(
    scheduler: ApifyScheduler,
    caplog: pytest.LogCaptureFixture,
    rq: mock.AsyncMock,
) -> None:
    """A request that cannot be converted (non-serializable meta) is not enqueued: returns False and logs a warning."""
    # A set in `meta` is not JSON-serializable, so `to_apify_request` returns None.
    scrapy_request = Request(url='https://example.com', meta={'tags': {'a', 'b'}})

    with caplog.at_level(logging.WARNING, logger='apify.scrapy.scheduler'):
        result = scheduler.enqueue_request(scrapy_request)

    assert result is False
    assert 'could not be converted' in caplog.text
    rq.add_request.assert_not_called()


def test_enqueue_request_enqueues_converted_request(scheduler: ApifyScheduler, rq: mock.AsyncMock) -> None:
    """A convertible request is enqueued and reported as newly added when the queue had not seen it."""
    rq.add_request.return_value = SimpleNamespace(was_already_present=False)

    result = scheduler.enqueue_request(Request(url='https://example.com'))

    assert result is True
    rq.add_request.assert_called_once()


def test_enqueue_request_returns_false_for_duplicate(scheduler: ApifyScheduler, rq: mock.AsyncMock) -> None:
    """A request already present in the queue is reported as not newly enqueued (returns False)."""
    rq.add_request.return_value = SimpleNamespace(was_already_present=True)

    result = scheduler.enqueue_request(Request(url='https://example.com'))

    assert result is False


def test_next_request_skips_request_that_fails_to_convert(
    scheduler: ApifyScheduler,
    caplog: pytest.LogCaptureFixture,
    rq: mock.AsyncMock,
) -> None:
    """A queue entry that fails to reconstruct is skipped and still marked handled, not retried forever."""
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


def test_next_request_returns_converted_request(scheduler: ApifyScheduler, rq: mock.AsyncMock) -> None:
    """A valid RQ entry is reconstructed into a Scrapy request and left unhandled until Scrapy is done."""
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


def test_next_request_returns_none_when_queue_empty(scheduler: ApifyScheduler, rq: mock.AsyncMock) -> None:
    """An empty queue makes `next_request` return None and skip marking anything as handled."""
    rq.fetch_next_request.return_value = None

    result = scheduler.next_request()

    assert result is None
    rq.mark_request_as_handled.assert_not_called()


def test_next_request_logs_exception_before_propagating(
    scheduler: ApifyScheduler,
    caplog: pytest.LogCaptureFixture,
    rq: mock.AsyncMock,
) -> None:
    """A failure in the coroutine run is logged with its traceback via `logger.exception` before propagating."""
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
    stub_scheduler_dependencies(monkeypatch)
    async_thread_cls = mock.Mock(side_effect=fake_async_thread)
    monkeypatch.setattr('apify.scrapy.scheduler.AsyncThread', async_thread_cls)

    crawler = fake_crawler()
    crawler.settings = Settings({'APIFY_ASYNC_THREAD_TIMEOUT_SECS': 123})
    ApifyScheduler.from_crawler(crawler)

    async_thread_cls.assert_called_once_with(default_timeout=timedelta(seconds=123))


APIFY_REQUESTS = [
    ApifyRequest(
        url=f'https://example.com/{index}',
        method='GET',
        unique_key=f'https://example.com/{index}',
        user_data={},
    )
    for index in range(4)
]


def hand_out(scheduler: ApifyScheduler, rq: mock.AsyncMock, count: int) -> list[Request]:
    """Fetch `count` requests, keeping each busy in Scrapy so it is not resolved as it is handed over.

    Returns the Scrapy requests, and leaves the crawler double reporting all of them as busy in the downloader.
    """
    rq.fetch_next_request.side_effect = APIFY_REQUESTS[:count]

    busy: set[Request] = set()
    scheduler._crawler = fake_crawler(downloader_busy=busy)

    for _ in range(count):
        scrapy_request = scheduler.next_request()
        assert scrapy_request is not None
        busy.add(scrapy_request)

    rq.fetch_next_request.side_effect = None
    rq.fetch_next_request.return_value = None

    return list(busy)


def test_has_pending_requests_marks_finished_requests_as_handled(scheduler: ApifyScheduler, rq: mock.AsyncMock) -> None:
    """Requests Scrapy has finished with are marked as handled once it goes idle and asks about pending work."""
    rq.fetch_next_request.return_value = APIFY_REQUESTS[0]
    scheduler.next_request()
    rq.mark_request_as_handled.assert_not_called()

    # Scrapy asks about pending work only once its downloader and its scraper are both idle.
    scheduler._crawler = fake_crawler(scraper_busy=set())
    rq.is_finished.return_value = True
    assert scheduler.has_pending_requests() is False

    rq.mark_request_as_handled.assert_called_once_with(APIFY_REQUESTS[0])


def test_next_request_marks_finished_requests_without_blocking(
    scheduler: ApifyScheduler,
    rq: mock.AsyncMock,
    async_thread: mock.Mock,
) -> None:
    """On the crawl's hot path a finished request is marked as handled without blocking the reactor on it."""
    (scrapy_request,) = hand_out(scheduler, rq, 1)

    # Scrapy is still downloading the request, so it stays unresolved.
    scheduler._crawler = fake_crawler(downloader_busy={scrapy_request})
    assert scheduler.next_request() is None
    rq.mark_request_as_handled.assert_not_called()

    # Scrapy is done with it, so it is resolved off the reactor thread instead of blocking on the round trip.
    scheduler._crawler = fake_crawler(scraper_busy=set())
    async_thread.reset_mock()
    assert scheduler.next_request() is None

    rq.mark_request_as_handled.assert_called_once_with(APIFY_REQUESTS[0])
    assert 'submit_coro' in called_methods(async_thread)


def test_has_pending_requests_waits_for_the_non_blocking_updates(
    scheduler: ApifyScheduler,
    rq: mock.AsyncMock,
    async_thread: mock.Mock,
) -> None:
    """The RQ is asked whether it is finished only after the updates fired off on the hot path have landed."""
    scheduler._crawler = fake_crawler()

    rq.is_finished.return_value = True
    assert scheduler.has_pending_requests() is False

    # The RQ answers from its own bookkeeping, which a pending update has not reached yet.
    assert called_methods(async_thread) == ['wait_for_submitted', 'run_coro']


@pytest.mark.parametrize(
    'busy_kwarg',
    [
        pytest.param('downloader_busy', id='busy in the downloader'),
        pytest.param('scraper_busy', id='busy in the scraper slot'),
    ],
)
def test_close_reclaims_requests_scrapy_never_finished(
    scheduler: ApifyScheduler,
    busy_kwarg: str,
    rq: mock.AsyncMock,
) -> None:
    """Requests still being processed when the scheduler closes go back to the RQ instead of being lost."""
    (scrapy_request,) = hand_out(scheduler, rq, 1)

    # Scrapy is still working on the request when the run is interrupted.
    scheduler._crawler = fake_crawler(**{busy_kwarg: {scrapy_request}})

    scheduler.close('shutdown')

    rq.reclaim_request.assert_called_once_with(APIFY_REQUESTS[0])
    rq.mark_request_as_handled.assert_not_called()


def test_close_marks_the_requests_scrapy_finished_as_handled(scheduler: ApifyScheduler, rq: mock.AsyncMock) -> None:
    """Requests Scrapy drained before the shutdown are marked as handled rather than reclaimed."""
    hand_out(scheduler, rq, 1)

    # Scrapy drains its downloader and its scraper before the scheduler is closed.
    scheduler._crawler = fake_crawler(scraper_busy=set())

    scheduler.close('finished')

    rq.mark_request_as_handled.assert_called_once_with(APIFY_REQUESTS[0])
    rq.reclaim_request.assert_not_called()


def test_close_reclaims_the_other_requests_after_a_failed_reclaim(
    scheduler: ApifyScheduler,
    caplog: pytest.LogCaptureFixture,
    rq: mock.AsyncMock,
) -> None:
    """One failing reclaim does not stop the other in-flight requests from going back to the RQ."""
    hand_out(scheduler, rq, 2)
    rq.reclaim_request.side_effect = [RuntimeError('boom'), None]

    with caplog.at_level(logging.ERROR, logger='apify.scrapy.scheduler'):
        scheduler.close('shutdown')

    assert rq.reclaim_request.call_count == 2
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(errors) == 1


def test_close_reaches_the_rq_in_one_round_trip_per_operation(
    scheduler: ApifyScheduler,
    rq: mock.AsyncMock,
    async_thread: mock.Mock,
) -> None:
    """Marks and reclaims each travel together, as a migration may not leave room for one round trip each."""
    handed_out = hand_out(scheduler, rq, 4)

    # Scrapy finished half of the requests and is still working on the rest when the run is interrupted.
    scheduler._crawler = fake_crawler(downloader_busy=set(handed_out[2:]))

    async_thread.reset_mock()
    scheduler.close('shutdown')

    assert rq.mark_request_as_handled.await_count == 2
    assert rq.reclaim_request.await_count == 2
    assert called_methods(async_thread).count('run_coro') == 2


def test_close_waits_for_the_non_blocking_updates(scheduler: ApifyScheduler, async_thread: mock.Mock) -> None:
    """The event loop is not torn down before the updates fired off on the hot path have landed."""
    scheduler.close('finished')

    methods = called_methods(async_thread)
    assert methods.index('wait_for_submitted') < methods.index('close')


def test_a_failed_mark_keeps_the_request_tracked(
    scheduler: ApifyScheduler,
    caplog: pytest.LogCaptureFixture,
    rq: mock.AsyncMock,
) -> None:
    """A request whose mark-as-handled fails stays tracked, so the next resolution retries it."""
    hand_out(scheduler, rq, 1)

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
    rq: mock.AsyncMock,
) -> None:
    """A hot-path mark that fails on its way to the RQ is retried, instead of leaving the request in progress."""
    hand_out(scheduler, rq, 1)

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
    crawler = fake_crawler()
    crawler.engine = SimpleNamespace(downloader=SimpleNamespace(), scraper=SimpleNamespace())

    with pytest.raises(RuntimeError, match='engine internals'):
        ApifyScheduler(crawler=crawler).open(spider)


def test_from_crawler_keeps_the_crawler(monkeypatch: pytest.MonkeyPatch) -> None:
    """`from_crawler` keeps the crawler, which is how the scheduler learns what Scrapy is still working on."""
    stub_scheduler_dependencies(monkeypatch)

    crawler = fake_crawler()
    scheduler = ApifyScheduler.from_crawler(crawler)

    assert scheduler._crawler is crawler


def test_open_listens_for_the_migration_and_the_abort(monkeypatch: pytest.MonkeyPatch, spider: DummySpider) -> None:
    """`open` registers the listeners with the Actor, so the scheduler learns when the run is moving or aborting."""
    actor = stub_scheduler_dependencies(monkeypatch)
    scheduler = ApifyScheduler(crawler=fake_crawler(scraper_busy=set()))

    scheduler.open(spider)

    assert actor.on.call_args_list == [
        mock.call(Event.MIGRATING, scheduler._on_migrating),
        mock.call(Event.ABORTING, scheduler._on_aborting),
    ]


def test_close_stops_listening_for_the_migration_and_the_abort(
    monkeypatch: pytest.MonkeyPatch,
    spider: DummySpider,
) -> None:
    """`close` unregisters the listeners, so a closed scheduler is not told about a migration or an abort."""
    actor = stub_scheduler_dependencies(monkeypatch)
    scheduler = ApifyScheduler(crawler=fake_crawler(scraper_busy=set()))
    scheduler.open(spider)

    scheduler.close('finished')

    assert actor.off.call_args_list == [
        mock.call(Event.MIGRATING, scheduler._on_migrating),
        mock.call(Event.ABORTING, scheduler._on_aborting),
    ]


def test_open_warns_when_the_actor_is_not_initialized(
    monkeypatch: pytest.MonkeyPatch,
    spider: DummySpider,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Without an initialized Actor there is nothing to register the listeners with, and that is said."""
    actor = stub_scheduler_dependencies(monkeypatch)
    actor.on.side_effect = RuntimeError('The _ActorType is not active.')
    scheduler = ApifyScheduler(crawler=fake_crawler(scraper_busy=set()))

    with caplog.at_level(logging.WARNING, logger='apify.scrapy.scheduler'):
        scheduler.open(spider)
    scheduler.close('finished')

    assert 'Actor is not initialized' in caplog.text
    actor.off.assert_not_called()


async def test_migration_settles_the_requests_as_scrapy_finishes_them(
    scheduler: ApifyScheduler,
    monkeypatch: pytest.MonkeyPatch,
    rq: mock.AsyncMock,
) -> None:
    """Once a migration is announced, nothing more goes out and the requests Scrapy holds are marked as they finish."""
    monkeypatch.setattr('apify.scrapy.scheduler.SETTLE_POLL_INTERVAL', timedelta(milliseconds=10))
    busy = set(hand_out(scheduler, rq, 2))
    scheduler._crawler = fake_crawler(downloader_busy=busy)
    (first_apify, first), (second_apify, second) = scheduler._requests_in_flight
    rq.fetch_next_request.reset_mock()

    settled = asyncio.create_task(scheduler._on_migrating(EventMigratingData(time_remaining=timedelta(seconds=27))))
    await asyncio.sleep(0.05)

    rq.mark_request_as_handled.assert_not_called()
    assert not settled.done()

    # The RQ is not even asked for more work.
    rq.fetch_next_request.return_value = APIFY_REQUESTS[2]
    assert scheduler.next_request() is None
    rq.fetch_next_request.assert_not_called()

    busy.discard(first)
    await asyncio.sleep(0.05)
    rq.mark_request_as_handled.assert_called_once_with(first_apify)
    assert not settled.done()

    busy.discard(second)
    await asyncio.wait_for(settled, timeout=1)
    assert rq.mark_request_as_handled.call_args_list == [mock.call(first_apify), mock.call(second_apify)]


async def test_abort_settles_the_requests_as_scrapy_finishes_them(
    scheduler: ApifyScheduler,
    monkeypatch: pytest.MonkeyPatch,
    rq: mock.AsyncMock,
) -> None:
    """Once an abort is announced, the requests Scrapy holds are marked as handled as they finish, not at the end."""
    monkeypatch.setattr('apify.scrapy.scheduler.SETTLE_POLL_INTERVAL', timedelta(milliseconds=10))
    busy = set(hand_out(scheduler, rq, 2))
    scheduler._crawler = fake_crawler(downloader_busy=busy)
    (first_apify, first), (second_apify, second) = scheduler._requests_in_flight

    settled = asyncio.create_task(scheduler._on_aborting())
    await asyncio.sleep(0.05)

    rq.mark_request_as_handled.assert_not_called()
    assert not settled.done()

    busy.discard(first)
    await asyncio.sleep(0.05)
    rq.mark_request_as_handled.assert_called_once_with(first_apify)
    assert not settled.done()

    busy.discard(second)
    await asyncio.wait_for(settled, timeout=1)
    assert rq.mark_request_as_handled.call_args_list == [mock.call(first_apify), mock.call(second_apify)]


async def test_a_repeated_migration_announcement_does_not_settle_again(
    scheduler: ApifyScheduler,
    monkeypatch: pytest.MonkeyPatch,
    rq: mock.AsyncMock,
) -> None:
    """A second announcement, e.g. a reboot during a migration, returns at once while the first one keeps settling."""
    monkeypatch.setattr('apify.scrapy.scheduler.SETTLE_POLL_INTERVAL', timedelta(milliseconds=10))
    hand_out(scheduler, rq, 1)

    settled = asyncio.create_task(scheduler._on_migrating(EventMigratingData()))
    await asyncio.sleep(0.05)

    await asyncio.wait_for(scheduler._on_migrating(EventMigratingData()), timeout=1)
    assert not settled.done()

    scheduler.close('shutdown')
    await asyncio.wait_for(settled, timeout=1)


async def test_migration_with_nothing_in_flight_only_stops_handing_out_requests(
    scheduler: ApifyScheduler,
    rq: mock.AsyncMock,
) -> None:
    """With nothing in flight the migration listener returns at once; the RQ is still not asked for more work."""
    await asyncio.wait_for(scheduler._on_migrating(EventMigratingData()), timeout=1)

    rq.fetch_next_request.return_value = APIFY_REQUESTS[0]
    assert scheduler.next_request() is None
    rq.fetch_next_request.assert_not_called()


async def test_close_ends_the_migration_settling(
    scheduler: ApifyScheduler,
    monkeypatch: pytest.MonkeyPatch,
    rq: mock.AsyncMock,
) -> None:
    """Closing the scheduler while it settles a migration ends the settling; `close` resolves the rest itself."""
    monkeypatch.setattr('apify.scrapy.scheduler.SETTLE_POLL_INTERVAL', timedelta(milliseconds=10))
    hand_out(scheduler, rq, 1)

    settled = asyncio.create_task(scheduler._on_migrating(EventMigratingData()))
    await asyncio.sleep(0.05)
    assert not settled.done()

    scheduler.close('shutdown')
    await asyncio.wait_for(settled, timeout=1)

    rq.mark_request_as_handled.assert_not_called()
    rq.reclaim_request.assert_called_once_with(APIFY_REQUESTS[0])
