from __future__ import annotations  # noqa: I001

from scrapy.crawler import CrawlerRunner
from scrapy.utils.defer import deferred_to_future

from apify import Actor
from apify.scrapy import apply_apify_settings

from .spiders import Spider  # ty: ignore[unresolved-import]


async def main() -> None:
    async with Actor:
        settings = apply_apify_settings()
        runner = CrawlerRunner(settings)
        await deferred_to_future(runner.crawl(Spider, start_urls=['http://localhost:8080/']))
