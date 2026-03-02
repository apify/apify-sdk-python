from __future__ import annotations

import os

from scrapy.crawler import AsyncCrawlerRunner

from .spiders import Spider  # ty: ignore[unresolved-import]
from apify import Actor
from apify.scrapy import apply_apify_settings


async def main() -> None:
    async with Actor:
        os.environ['SCRAPY_SETTINGS_MODULE'] = 'src.settings_custom_pipeline'
        settings = apply_apify_settings()
        runner = AsyncCrawlerRunner(settings)
        await runner.crawl(Spider, start_urls=['http://localhost:8080/'])
