from __future__ import annotations

import asyncio

from scrapy.crawler import AsyncCrawlerRunner

from apify import Actor
from apify.scrapy import apply_apify_settings

# Import your Scrapy spider here.
from .spiders import TitleSpider as Spider


async def main() -> None:
    """Apify Actor main coroutine for executing the Scrapy spider."""
    async with Actor:
        # Retrieve and process Actor input.
        actor_input = await Actor.get_input() or {}
        start_urls = [url['url'] for url in actor_input.get('startUrls', [])]
        allowed_domains = actor_input.get('allowedDomains')
        proxy_config = actor_input.get('proxyConfiguration')

        # Apply Apify settings, which will override the Scrapy project settings.
        settings = apply_apify_settings(proxy_config=proxy_config)

        # Create AsyncCrawlerRunner and execute the Scrapy spider.
        crawler_runner = AsyncCrawlerRunner(settings)
        await crawler_runner.crawl(
            Spider,
            start_urls=start_urls,
            allowed_domains=allowed_domains,
        )


if __name__ == '__main__':
    asyncio.run(main())
