from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .conftest import MakeActorFunction, RunActorFunction


async def test_migration_through_reboot(make_actor: MakeActorFunction, run_actor: RunActorFunction) -> None:
    """Test that actor works as expected after migration through testing behavior after reboot.

    Handle two requests. Migrate in between the two requests."""

    async def main() -> None:
        from crawlee._types import BasicCrawlingContext, ConcurrencySettings
        from crawlee.crawlers import BasicCrawler

        from apify import Actor

        async with Actor:
            crawler = BasicCrawler(concurrency_settings=ConcurrencySettings(max_concurrency=1))
            requests = ['https://example.com/1', 'https://example.com/2']

            run = await Actor.apify_client.run(Actor.configuration.actor_run_id or '').get()
            assert run
            first_run = run.get('stats', {}).get('rebootCount', 0) == 0
            Actor.log.warning(run)

            @crawler.router.default_handler
            async def default_handler(context: BasicCrawlingContext) -> None:
                context.log.info(f'Processing {context.request.url} ...')

                # Simulate migration through reboot
                if context.request.url == requests[1] and first_run:
                    context.log.info(f'Reclaiming {context.request.url} ...')
                    rq = await crawler.get_request_manager()
                    await rq.reclaim_request(context.request)
                    await Actor.reboot()

            await crawler.run(requests)

            # Each time one request is finished.
            assert crawler.statistics.state.requests_finished == 1

    actor = await make_actor(label='migration', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'
