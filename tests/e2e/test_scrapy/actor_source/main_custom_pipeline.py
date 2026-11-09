from __future__ import annotations

import os

from scrapy.crawler import AsyncCrawlerRunner

from .spiders import Spider  # ty: ignore[import-not-found]
from apify import Actor
from apify.scrapy import apply_apify_settings


async def main() -> None:
    async with Actor:
        os.environ['SCRAPY_SETTINGS_MODULE'] = 'actor.settings_custom_pipeline'
        settings = apply_apify_settings()
        runner = AsyncCrawlerRunner(settings)
        await runner.crawl(Spider, start_urls=['http://localhost:8080/'])
