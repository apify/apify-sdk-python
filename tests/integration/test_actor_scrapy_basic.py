from __future__ import annotations

from typing import TYPE_CHECKING

from scrapy.crawler import CrawlerProcess

from .actor_scrapy_source_base.src.spiders.title import TitleSpider as Spider
from apify import Actor
from apify.scrapy.utils import apply_apify_settings

if TYPE_CHECKING:
    from .conftest import ActorFactory

# Default input values for local execution using `apify run`
LOCAL_DEFAULT_START_URLS = [{'url': 'https://apify.com'}]


class TestActorScrapyBasic:
    async def test_actor_scrapy_basic(self: TestActorScrapyBasic, make_actor: ActorFactory) -> None:
        async def main() -> None:
            async with Actor:
                Actor.log.info('Actor is being executed...')

                # Process Actor input
                actor_input = await Actor.get_input() or {}
                start_urls = actor_input.get('startUrls', LOCAL_DEFAULT_START_URLS)
                proxy_config = actor_input.get('proxyConfiguration')

                # Add start URLs to the request queue
                rq = await Actor.open_request_queue()
                for start_url in start_urls:
                    url = start_url.get('url')
                    await rq.add_request(request={'url': url, 'method': 'GET'})

                # Apply Apify settings, it will override the Scrapy project settings
                settings = apply_apify_settings(proxy_config=proxy_config)

                # Execute the spider using Scrapy CrawlerProcess
                process = CrawlerProcess(settings, install_root_handler=False)
                process.crawl(Spider)
                process.start()

        actor = await make_actor('actor-scrapy-basic', main_func=main)
        run_result = await actor.call()

        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'
