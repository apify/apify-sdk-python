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
                max_requests_per_crawl=3,
                concurrency_settings=ConcurrencySettings(max_concurrency=1, desired_concurrency=1),
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
