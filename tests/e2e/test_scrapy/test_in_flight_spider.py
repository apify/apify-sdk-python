from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from ..._utils import poll_until_condition
from .actor_source.spider_in_flight import IN_FLIGHT_LOG_MARKER
from .conftest import get_scrapy_source_files

if TYPE_CHECKING:
    from apify_client import ApifyClientAsync

    from ..conftest import MakeActorFunction


async def test_in_flight_spider(make_actor: MakeActorFunction, apify_client_async: ApifyClientAsync) -> None:
    """A request Scrapy is still downloading when the run is aborted stays pending in the request queue."""
    actor = await make_actor(
        label='scrapy-in-flight',
        source_files=get_scrapy_source_files('spider_in_flight.py', 'InFlightSpider'),
        additional_requirements=['scrapy>=2.14.0'],
    )
    run = await actor.start()
    run_client = apify_client_async.run(run.id)

    # Interrupt the run only once Scrapy holds the request, otherwise there would be nothing to lose. The container
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

    await run_client.abort()
    run_result = await run_client.wait_for_finish(wait_duration=timedelta(seconds=600))
    assert run_result is not None
    assert run_result.status == 'ABORTED'

    # The queue's request counters are eventually consistent, so read the request itself.
    assert run.default_request_queue_id is not None
    requests = await apify_client_async.request_queue(run.default_request_queue_id).list_requests()
    assert [request.url for request in requests.items] == ['http://localhost:8080/slow']
    (slow_request,) = requests.items
    assert slow_request.handled_at is None, f'The interrupted request was marked as handled: {slow_request}'
