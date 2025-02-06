"""Main entry point for the Apify Actor & Scrapy integration.

This module defines the main coroutine for the Apify Scrapy Actor, executed from the __main__.py file. The coroutine
processes the Actor's input and executes the Scrapy spider. Additionally, it updates Scrapy project settings by
applying Apify-related settings. Which includes adding a custom scheduler, retry middleware, and an item pipeline
for pushing data to the Apify dataset.

Customization:
--------------

Feel free to customize this file to add specific functionality to the Actor, such as incorporating your own Scrapy
components like spiders and handling Actor input. However, make sure you have a clear understanding of your
modifications. For instance, removing `apply_apify_settings` break the integration between Scrapy and Apify.

Documentation:
--------------

For an in-depth description of the Apify-Scrapy integration process, our Scrapy components, known limitations and
other stuff, please refer to the following documentation page: https://docs.apify.com/cli/docs/integrating-scrapy.
"""
# ruff: noqa: I001

from __future__ import annotations

from scrapy.crawler import CrawlerRunner
from scrapy.utils.defer import deferred_to_future

from apify import Actor
from apify.scrapy.utils import apply_apify_settings

# Import your Scrapy spider here.
from .spiders.title import TitleSpider as Spider


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

        # Create CrawlerRunner and execute the Scrapy spider.
        crawler_runner = CrawlerRunner(settings)
        crawl_deferred = crawler_runner.crawl(
            Spider,
            start_urls=start_urls,
            allowed_domains=allowed_domains,
        )
        await deferred_to_future(crawl_deferred)
