from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import TYPE_CHECKING

from ..._utils import poll_until_condition
from .actor_source.main_delayed_chain_crawler import IN_FLIGHT_LOG_MARKER
from .conftest import read_actor_source

if TYPE_CHECKING:
    from apify_client import ApifyClientAsync

    from ..conftest import MakeActorFunction


async def test_graceful_abort_crawler(make_actor: MakeActorFunction, apify_client_async: ApifyClientAsync) -> None:
    """A graceful abort persists the crawler statistics, and every handled request has its item pushed exactly once."""
    actor = await make_actor(
        label='crawl-graceful-abort',
        source_files={
            'actor/main.py': read_actor_source('main_delayed_chain_crawler.py'),
        },
    )
    run = await actor.start()
    run_client = apify_client_async.run(run.id)

    # The crawler handles one request at a time, so once it starts the third page, the first two are handled. The
    # container startup time is highly variable, so poll the log with a growing interval.
    third_page_marker = f'{IN_FLIGHT_LOG_MARKER}: http://localhost:8080/delayed/3'
    log_client = run_client.log()
    log = await poll_until_condition(
        log_client.get,
        lambda log: bool(log and third_page_marker in log),
        timeout=300,
        poll_interval=2,
        backoff_factor=1.2,
    )
    assert log is not None
    assert third_page_marker in log, f'The run did not log {third_page_marker!r} in time:\n{log}'

    await run_client.abort(gracefully=True)
    run_result = await run_client.wait_for_finish(wait_duration=timedelta(seconds=600))
    assert run_result is not None
    assert run_result.status == 'ABORTED'

    assert run.default_request_queue_id is not None
    requests = await apify_client_async.request_queue(run.default_request_queue_id).list_requests()
    handled_urls = [request.url for request in requests.items if request.handled_at is not None]
    pending_urls = [request.url for request in requests.items if request.handled_at is None]
    assert len(handled_urls) >= 2, f'Fewer than two requests were marked as handled: {requests.items}'
    assert pending_urls, f'No request stayed pending: {requests.items}'

    items = await poll_until_condition(
        run_client.dataset().list_items,
        lambda page: len(page.items) >= len(handled_urls),
        timeout=30,
    )
    assert Counter(item['url'] for item in items.items) == Counter(handled_urls)

    # The platform sends `persistState` with the abort, and the crawler persists its statistics in the default KVS.
    kvs_client = run_client.key_value_store()
    keys = await kvs_client.list_keys()
    statistics_keys = [item.key for item in keys.items if 'CRAWLER_STATISTICS' in item.key]
    assert len(statistics_keys) == 1, f'Expected one crawler statistics record: {[item.key for item in keys.items]}'
    statistics_record = await kvs_client.get_record(statistics_keys[0])
    assert statistics_record is not None
    requests_finished = statistics_record['value']['requestsFinished']
    assert 2 <= requests_finished <= len(handled_urls), f'requestsFinished={requests_finished}'
