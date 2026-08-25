from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import TYPE_CHECKING

from ..._utils import poll_until_condition
from .actor_source.spider_delayed_chain import IN_FLIGHT_LOG_MARKER
from .conftest import get_scrapy_source_files

if TYPE_CHECKING:
    from apify_client import ApifyClientAsync

    from ..conftest import MakeActorFunction


async def test_graceful_abort_spider(make_actor: MakeActorFunction, apify_client_async: ApifyClientAsync) -> None:
    """A graceful abort lets the request in flight finish and marks it as handled, then the crawl closes on its own."""
    actor = await make_actor(
        label='scrapy-graceful-abort',
        source_files=get_scrapy_source_files('spider_delayed_chain.py', 'DelayedChainSpider'),
        additional_requirements=['scrapy>=2.14.0'],
    )
    run = await actor.start()
    run_client = apify_client_async.run(run.id)

    # Abort the run only once Scrapy holds a request, otherwise there would be nothing to finish. The container
    # startup time is highly variable, so poll the log with a growing interval.
    log_client = run_client.log()
    log = await poll_until_condition(
        log_client.get,
        lambda log: bool(log and IN_FLIGHT_LOG_MARKER in log),
        timeout=300,
        poll_interval=2,
        backoff_factor=1.2,
    )
    assert log is not None
    assert IN_FLIGHT_LOG_MARKER in log, f'The run did not log {IN_FLIGHT_LOG_MARKER!r} in time:\n{log}'

    await run_client.abort(gracefully=True)
    run_result = await run_client.wait_for_finish(wait_duration=timedelta(seconds=600))
    assert run_result is not None
    assert run_result.status == 'ABORTED'

    # The crawl stopped gracefully before the platform killed the process.
    log = await log_client.get()
    assert log is not None
    assert 'Spider closed (shutdown)' in log, f'The crawl did not close gracefully:\n{log}'

    # Every request Scrapy finished pushed its item exactly once, and the rest of the chain stays pending.
    assert run.default_request_queue_id is not None
    requests = await apify_client_async.request_queue(run.default_request_queue_id).list_requests()
    handled_urls = [request.url for request in requests.items if request.handled_at is not None]
    pending_urls = [request.url for request in requests.items if request.handled_at is None]
    items = await run_client.dataset().list_items()

    assert handled_urls, f'No request was marked as handled: {requests.items}'
    assert Counter(item['url'] for item in items.items) == Counter(handled_urls)
    assert pending_urls, f'No request stayed pending: {requests.items}'
