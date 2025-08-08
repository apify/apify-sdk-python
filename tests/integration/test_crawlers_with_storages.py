from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .conftest import MakeActorFunction, RunActorFunction


async def test_actor_on_platform_max_crawl_depth(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test that the actor respects max_crawl_depth."""

    async def main() -> None:
        """The crawler entry point."""
        import re

        from crawlee.crawlers import ParselCrawler, ParselCrawlingContext

        from apify import Actor

        async with Actor:
            crawler = ParselCrawler(max_crawl_depth=2)
            finished = []
            enqueue_pattern = re.compile(r'http://localhost:8080/2+$')

            @crawler.router.default_handler
            async def default_handler(context: ParselCrawlingContext) -> None:
                """Default request handler."""
                context.log.info(f'Processing {context.request.url} ...')
                await context.enqueue_links(include=[enqueue_pattern])
                finished.append(context.request.url)

            await crawler.run(['http://localhost:8080/'])
            assert finished == ['http://localhost:8080/', 'http://localhost:8080/2', 'http://localhost:8080/22']

    actor = await make_actor(label='crawler-max-depth', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_actor_on_platform_max_requests_per_crawl(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test that the actor respects max_requests_per_crawl."""

    async def main() -> None:
        """The crawler entry point."""
        from crawlee import ConcurrencySettings
        from crawlee.crawlers import ParselCrawler, ParselCrawlingContext

        from apify import Actor

        async with Actor:
            crawler = ParselCrawler(
                max_requests_per_crawl=3, concurrency_settings=ConcurrencySettings(max_concurrency=1)
            )
            finished = []

            @crawler.router.default_handler
            async def default_handler(context: ParselCrawlingContext) -> None:
                """Default request handler."""
                context.log.info(f'Processing {context.request.url} ...')
                await context.enqueue_links()
                finished.append(context.request.url)

            await crawler.run(['http://localhost:8080/'])
            assert len(finished) == 3

    actor = await make_actor(label='crawler-max-requests', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_actor_on_platform_max_request_retries(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test that the actor respects max_request_retries."""

    async def main() -> None:
        """The crawler entry point."""
        from crawlee.crawlers import BasicCrawlingContext, ParselCrawler, ParselCrawlingContext

        from apify import Actor

        async with Actor:
            max_retries = 3
            crawler = ParselCrawler(max_request_retries=max_retries)
            failed_counter = 0

            @crawler.error_handler
            async def error_handler(_: BasicCrawlingContext, __: Exception) -> None:
                nonlocal failed_counter
                failed_counter += 1

            @crawler.router.default_handler
            async def default_handler(_: ParselCrawlingContext) -> None:
                raise RuntimeError('Some error')

            await crawler.run(['http://localhost:8080/'])
            assert failed_counter == max_retries, f'{failed_counter=}'

    actor = await make_actor(label='crawler-max-retries', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_a() -> None:
    """Test that the actor respects max_request_retries."""

    from apify import Actor

    async with Actor:
        rq = await Actor.open_request_queue(name='asdasdd', force_cloud=True)
        await rq.drop()
        rq = await Actor.open_request_queue(name='asdasdd', force_cloud=True)
        Actor.log.info('Request queue opened')

        # Add initial requests
        await rq.add_request('https://example.com/1')
        await rq.add_request('https://example.com/2')
        Actor.log.info('Added initial requests')

        # Fetch one and reclaim to forefront
        request1 = await rq.fetch_next_request()
        assert request1 is not None, f'request1={request1}'
        assert request1.url == 'https://example.com/1', f'request1.url={request1.url}'
        Actor.log.info(f'Fetched request: {request1.url}')

        await rq.reclaim_request(request1, forefront=True)
        Actor.log.info('Reclaimed request to forefront')

        # Add forefront request
        await rq.add_request('https://example.com/priority', forefront=True)
        Actor.log.info('Added new forefront request')

        # Fetch all requests and verify forefront behavior
        urls_ordered = list[str]()
        while next_request := await rq.fetch_next_request():
            urls_ordered.append(next_request.url)
            await rq.mark_request_as_handled(next_request)

        Actor.log.info(f'Final order of fetched URLs: {urls_ordered}')

        # Verify that we got all 3 requests
        assert len(urls_ordered) == 3, f'len(urls_ordered)={len(urls_ordered)}'

        assert urls_ordered[0] == 'https://example.com/priority', f'urls_ordered[0]={urls_ordered[0]}'
        assert urls_ordered[1] == request1.url, (
            f'urls_ordered[1]={urls_ordered[1]}',
            f'request1.url={request1.url}',
        )
        assert urls_ordered[2] == 'https://example.com/2', f'urls_ordered[2]={urls_ordered[2]}'
        Actor.log.info('Request ordering verified successfully')
