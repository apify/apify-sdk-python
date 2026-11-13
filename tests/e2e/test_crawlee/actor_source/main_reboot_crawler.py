from __future__ import annotations

from crawlee import ConcurrencySettings
from crawlee.crawlers import ParselCrawler, ParselCrawlingContext

from apify import Actor

REBOOT_URL = 'http://localhost:8080/about'
"""The page whose handler reboots the first container, so part of the site is crawled before and part after."""


async def main() -> None:
    async with Actor:
        run = await Actor.apify_client.run(Actor.configuration.actor_run_id or '').get()
        assert run is not None, 'The Actor could not read its own run.'
        is_first_container = run.stats.reboot_count == 0

        # One request at a time, so no other request is in progress when the handler reboots the run.
        crawler = ParselCrawler(
            max_crawl_depth=2,
            concurrency_settings=ConcurrencySettings(max_concurrency=1, desired_concurrency=1),
        )

        @crawler.router.default_handler
        async def handler(context: ParselCrawlingContext) -> None:
            if context.request.url == REBOOT_URL and is_first_container:
                request_manager = await crawler.get_request_manager()
                await request_manager.reclaim_request(context.request)
                await Actor.reboot()

            await context.enqueue_links()

            if '/products/' in context.request.url:
                await context.push_data(
                    {
                        'url': context.request.url,
                        'name': context.selector.css('h1::text').get('').strip(),
                    }
                )

        await crawler.run(['http://localhost:8080/'])

        await Actor.set_value(
            'CRAWLER_RESULT',
            {'requests_finished': crawler.statistics.state.requests_finished},
        )
