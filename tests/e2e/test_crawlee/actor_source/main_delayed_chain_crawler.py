from __future__ import annotations

from typing import TYPE_CHECKING

from crawlee import ConcurrencySettings
from crawlee.crawlers import ParselCrawler, ParselCrawlingContext

from apify import Actor

if TYPE_CHECKING:
    from crawlee.crawlers import BasicCrawlingContext

IN_FLIGHT_LOG_MARKER = 'Sending the request to the server'
"""Logged before every navigation, so a test knows which request is in flight."""


async def main() -> None:
    async with Actor:
        # One request at a time, so the test knows what is in flight when it interrupts the run.
        crawler = ParselCrawler(concurrency_settings=ConcurrencySettings(max_concurrency=1, desired_concurrency=1))

        @crawler.pre_navigation_hook
        async def mark_in_flight(context: BasicCrawlingContext) -> None:
            Actor.log.info(f'{IN_FLIGHT_LOG_MARKER}: {context.request.url}')

        @crawler.router.default_handler
        async def handler(context: ParselCrawlingContext) -> None:
            await context.push_data({'url': context.request.url})
            await context.enqueue_links()

        await crawler.run(['http://localhost:8080/delayed/1'])
