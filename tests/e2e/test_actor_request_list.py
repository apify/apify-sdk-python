from __future__ import annotations

from typing import TYPE_CHECKING

from .._utils import poll_until_condition
from apify import Actor

if TYPE_CHECKING:
    from apify_client import ApifyClientAsync

    from .conftest import MakeActorFunction, RunActorFunction

_EXPECTED_REQUESTS = [
    ('https://example.com/products/1', 'direct'),
    ('https://example.com/products/2', 'remote'),
    ('https://example.com/products/3', 'remote'),
]


async def test_request_list_from_actor_input(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
    apify_client_async: ApifyClientAsync,
) -> None:
    """Direct URLs and a `requestsFromUrl` list from the Actor input reach the crawler with their user data."""

    async def main() -> None:
        from crawlee.crawlers import BasicCrawler, BasicCrawlingContext

        from apify.request_loaders import ApifyRequestList

        async with Actor:
            actor_input = await Actor.get_input() or {}
            request_list = await ApifyRequestList.open(
                request_list_sources_input=actor_input.get('requestListSources', []),
            )
            crawler = BasicCrawler(request_manager=await request_list.to_tandem())

            # The handler only records the requests. It doesn't fetch them, so the URLs don't have to resolve.
            @crawler.router.default_handler
            async def handler(context: BasicCrawlingContext) -> None:
                await context.push_data({'url': context.request.url, 'source': context.request.user_data.get('source')})

            await crawler.run()

    actor = await make_actor(label='request-list', main_func=main)
    run_result = await run_actor(
        actor,
        run_input={
            'requestListSources': [
                {'url': 'https://example.com/products/1', 'userData': {'source': 'direct'}},
                {'requestsFromUrl': 'http://localhost:8080/start-urls.txt', 'userData': {'source': 'remote'}},
            ],
        },
    )
    assert run_result.status == 'SUCCEEDED'

    dataset = actor.last_run().dataset()
    items = await poll_until_condition(
        dataset.list_items,
        lambda page: len(page.items) >= len(_EXPECTED_REQUESTS),
        timeout=30,
    )
    assert sorted((item['url'], item['source']) for item in items.items) == _EXPECTED_REQUESTS

    # The tandem moves every request from the list into the default RQ and marks it as handled there.
    assert run_result.default_request_queue_id is not None
    rq_client = apify_client_async.request_queue(run_result.default_request_queue_id)
    requests = await rq_client.list_requests()
    handled_urls = sorted(request.url for request in requests.items if request.handled_at is not None)
    assert handled_urls == [url for url, _ in _EXPECTED_REQUESTS]
