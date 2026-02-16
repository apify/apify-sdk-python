from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scrapy import Request, Spider

if TYPE_CHECKING:
    from collections.abc import Generator

    from scrapy.http.response import Response


class CustomPipelineSpider(Spider):
    name = 'custom_pipeline_spider'

    def __init__(self, start_urls: list[str], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.start_urls = start_urls

    def start_requests(self) -> Generator[Request, None, None]:
        for url in self.start_urls:
            yield Request(url, callback=self.parse)

    def parse(self, response: Response) -> Generator[Request, None, None]:
        for link in response.css('a[href*="/products/"]::attr(href)').getall():
            yield response.follow(link, callback=self.parse_product)

    def parse_product(self, response: Response) -> Generator[dict, None, None]:
        yield {
            'url': response.url,
            'name': response.css('h1::text').get(''),
            'price': response.css('span.price::text').get(''),
            'description': response.css('p.description::text').get(''),
        }
