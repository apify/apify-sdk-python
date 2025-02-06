from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .conftest import MakeActorFunction, RunActorFunction


async def test_actor_scrapy_title_spider(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    actor_source_files = {
        'src/spiders/title.py': """
            from __future__ import annotations
            from typing import TYPE_CHECKING, Any
            from urllib.parse import urljoin
            from scrapy import Request, Spider
            from ..items import TitleItem

            if TYPE_CHECKING:
                from collections.abc import Generator
                from scrapy.responsetypes import Response


            class TitleSpider(Spider):
                name = 'title_spider'

                # Limit the number of pages to scrape.
                custom_settings = {'CLOSESPIDER_PAGECOUNT': 10}

                def __init__(
                    self,
                    start_urls: list[str],
                    allowed_domains: list[str],
                    *args: Any,
                    **kwargs: Any,
                ) -> None:
                    super().__init__(*args, **kwargs)
                    self.start_urls = start_urls
                    self.allowed_domains = allowed_domains

                def parse(self, response: Response) -> Generator[TitleItem | Request, None, None]:
                    self.logger.info('TitleSpider is parsing %s...', response)
                    url = response.url
                    title = response.css('title::text').extract_first()
                    yield TitleItem(url=url, title=title)

                    for link_href in response.css('a::attr("href")'):
                        link_url = urljoin(response.url, link_href.get())
                        if link_url.startswith(('http://', 'https://')):
                            yield Request(link_url)
        """,
        'src/spiders/__init__.py': """
            from .title import TitleSpider
        """,
        'src/items.py': """
            import scrapy

            class TitleItem(scrapy.Item):
                url = scrapy.Field()
                title = scrapy.Field()
        """,
        'src/settings.py': """
            BOT_NAME = 'titlebot'
            DEPTH_LIMIT = 1
            LOG_LEVEL = 'INFO'
            NEWSPIDER_MODULE = 'src.spiders'
            ROBOTSTXT_OBEY = True
            SPIDER_MODULES = ['src.spiders']
            TELNETCONSOLE_ENABLED = False
            TWISTED_REACTOR = 'twisted.internet.asyncioreactor.AsyncioSelectorReactor'
        """,
        'src/__init__.py': '',
        'src/main.py': """
            from __future__ import annotations
            from scrapy.crawler import CrawlerRunner
            from scrapy.utils.defer import deferred_to_future
            from apify import Actor
            from apify.scrapy.utils import apply_apify_settings
            from .spiders.title import TitleSpider as Spider


            async def main() -> None:
                async with Actor:
                    Actor.log.info('Actor is being executed...')

                    # Retrieve and process Actor input.
                    start_urls = ['https://crawlee.dev']
                    allowed_domains = ['crawlee.dev']
                    proxy_config = {'useApifyProxy': True}

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
        """,
        'src/__main__.py': """
            from __future__ import annotations
            from twisted.internet import asyncioreactor

            # Install Twisted's asyncio reactor before importing any other Twisted or Scrapy components.
            asyncioreactor.install()

            import os
            from apify.scrapy import initialize_logging, run_scrapy_actor
            from .main import main

            # Ensure the location to the Scrapy settings module is defined.
            os.environ['SCRAPY_SETTINGS_MODULE'] = 'src.settings'

            if __name__ == '__main__':
                initialize_logging()
                run_scrapy_actor(main())
        """,
    }

    actor = await make_actor('actor-scrapy-title-spider', source_files=actor_source_files)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'

    items = await actor.last_run().dataset().list_items()

    assert items.count >= 10

    for item in items.items:
        assert 'url' in item
        assert 'title' in item
