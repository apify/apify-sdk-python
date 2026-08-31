from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from .actor_source.spider_reboot import CHAIN_LENGTH, REBOOT_LOG_MARKER
from .conftest import get_scrapy_source_files

if TYPE_CHECKING:
    from apify_client import ApifyClientAsync

    from ..conftest import MakeActorFunction, RunActorFunction


async def test_reboot_spider(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
    apify_client_async: ApifyClientAsync,
) -> None:
    """A run rebooted mid-crawl settles the request in flight first and continues where it left off afterwards."""
    actor = await make_actor(
        label='scrapy-reboot',
        source_files=get_scrapy_source_files('spider_reboot.py', 'RebootSpider'),
        additional_requirements=['scrapy>=2.14.0'],
    )
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'

    # The reboot went through the scheduler's migration handling before the process was restarted.
    log = await actor.last_run().log().get()
    assert log is not None
    assert REBOOT_LOG_MARKER in log, f'The run did not reboot:\n{log}'
    assert 'The Actor run is migrating' in log, f'The scheduler did not react to the reboot:\n{log}'
    assert 'Scrapy has finished the requests it was working on' in log, f'The request in flight was not settled:\n{log}'

    # Each page of the chain was crawled once, the one in flight during the reboot included.
    expected_urls = [f'http://localhost:8080/delayed/{n}' for n in range(1, CHAIN_LENGTH + 1)]
    items = await actor.last_run().dataset().list_items()
    assert sorted(item['url'] for item in items.items) == expected_urls

    assert run_result.default_request_queue_id is not None
    requests = await apify_client_async.request_queue(run_result.default_request_queue_id).list_requests()
    assert Counter(request.url for request in requests.items) == Counter(expected_urls)
    assert all(request.handled_at is not None for request in requests.items), requests.items
