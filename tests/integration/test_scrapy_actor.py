from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from .conftest import MakeActorFunction, RunActorFunction


@pytest.mark.only
async def test_actor_scrapy_title_spider(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    actor_source_files = {
        'requirements.txt': """
            nest-asyncio ~= 1.6
            scrapy ~= 2.12
        """,
        'src/spiders/title.py': """
            from __future__ import annotations
            from typing import TYPE_CHECKING, Generator
            from scrapy import Request, Spider
            from ..items import TitleItem
            if TYPE_CHECKING:
                from scrapy.responsetypes import Response

            class TitleSpider(Spider):
                name = 'title_spider'
                start_urls = ['https://crawlee.dev/']

                def parse(self, response: Response) -> Generator[TitleItem | Request, None, None]:
                    self.logger.info('TitleSpider is parsing %s...', response)
                    url = response.url
                    title = response.css('title::text').get().strip()
                    yield TitleItem(url=url, title=title)
        """,
        'src/spiders/__init__.py': """
            from .title import TitleSpider
        """,
        'src/items.py': """
            import scrapy

            class TitleItem(scrapy.Item):
                url = scrapy.Field
                title = scrapy.Field()
        """,
        'src/settings.py': """
            BOT_NAME = 'title_scraper'
            LOG_LEVEL = 'INFO'
            SPIDER_MODULES = ['src.spiders']
            NEWSPIDER_MODULE = 'src.spiders'
            ROBOTSTXT_OBEY = True
            REQUEST_FINGERPRINTER_IMPLEMENTATION = '2.7'
            TWISTED_REACTOR = 'twisted.internet.asyncioreactor.AsyncioSelectorReactor'
            FEED_EXPORT_ENCODING = 'utf-8'
        """,
        'src/__init__.py': '',
        'src/main.py': """
            from __future__ import annotations
            from scrapy.crawler import CrawlerProcess
            from apify import Actor
            from apify.scrapy.utils import apply_apify_settings
            from .spiders.title import TitleSpider as Spider

            async def main() -> None:
                async with Actor:
                    Actor.log.info('Actor is being executed...')
                    request_queue = await Actor.open_request_queue()
                    await request_queue.add_request('https://crawlee.dev/')
                    settings = apply_apify_settings()
                    process = CrawlerProcess(settings, install_root_handler=False)
                    process.crawl(Spider)
                    process.start()
        """,
        'src/__main__.py': """
            from __future__ import annotations
            from logging import StreamHandler, getLogger
            from typing import Any
            from scrapy.utils import log as scrapy_logging
            from scrapy.utils.project import get_project_settings
            from apify.log import ActorLogFormatter

            MAIN_LOGGER_NAMES = ['apify', 'apify_client', 'scrapy']
            OTHER_LOGGER_NAMES = ['filelock', 'hpack', 'httpcore', 'httpx', 'protego', 'twisted']
            ALL_LOGGER_NAMES = MAIN_LOGGER_NAMES + OTHER_LOGGER_NAMES

            settings = get_project_settings()
            LOGGING_LEVEL = settings['LOG_LEVEL']

            apify_handler = StreamHandler()
            apify_handler.setFormatter(ActorLogFormatter(include_logger_name=True))


            def configure_logger(logger_name: str | None, log_level: str, *handlers: StreamHandler) -> None:
                logger = getLogger(logger_name)
                logger.setLevel(log_level)
                logger.handlers = []

                for handler in handlers:
                    logger.addHandler(handler)


            for logger_name in MAIN_LOGGER_NAMES:
                configure_logger(logger_name, LOGGING_LEVEL, apify_handler)

            old_configure_logging = scrapy_logging.configure_logging


            def new_configure_logging(*args: Any, **kwargs: Any) -> None:
                old_configure_logging(*args, **kwargs)
                configure_logger(None, LOGGING_LEVEL, apify_handler)
                for logger_name in ALL_LOGGER_NAMES:
                    configure_logger(logger_name, LOGGING_LEVEL)
                configure_logger('httpx', 'WARNING')


            scrapy_logging.configure_logging = new_configure_logging

            import asyncio
            import os
            import nest_asyncio
            from scrapy.utils.reactor import install_reactor
            from .main import main

            install_reactor('twisted.internet.asyncioreactor.AsyncioSelectorReactor')
            nest_asyncio.apply()

            os.environ['SCRAPY_SETTINGS_MODULE'] = 'src.settings'

            asyncio.run(main())
        """,
    }

    actor = await make_actor('actor-scrapy-title-spider', source_files=actor_source_files)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'

    items = await actor.last_run().dataset().list_items()

    assert items.count == 1
    assert items.items == {'blah'}
