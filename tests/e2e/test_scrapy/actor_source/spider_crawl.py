from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule

if TYPE_CHECKING:
    from collections.abc import Generator

    from scrapy.http.response import Response


class CrawlProductSpider(CrawlSpider):
    name = 'crawl_product_spider'

    rules = (Rule(LinkExtractor(allow=r'/products/'), callback='parse_product'),)

    def __init__(self, start_urls: list[str], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.start_urls = start_urls

    def parse_product(self, response: Response) -> Generator[dict, None, None]:
        yield {
            'url': response.url,
            'name': response.css('h1::text').get(''),
            'price': response.css('span.price::text').get(''),
            'description': response.css('p.description::text').get(''),
        }
