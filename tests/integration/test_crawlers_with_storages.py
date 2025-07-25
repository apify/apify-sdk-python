from tests.integration.conftest import MakeActorFunction, RunActorFunction


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
                await context.push_data({'Url': context.request.url})
                finished.append(context.request.url)

            await crawler.run(['http://localhost:8080/'])
            assert finished == ['http://localhost:8080/', 'http://localhost:8080/2', 'http://localhost:8080/22']
            # assert some dataset

    actor = await make_actor(label='parsel-crawler', main_func=main)
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
                await context.push_data({'Url': context.request.url})
                finished.append(context.request.url)

            await crawler.run(['http://localhost:8080/'])
            assert len(finished) == 3
            # assert some dataset

    actor = await make_actor(label='parsel-crawler', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'
