from __future__ import annotations  # noqa: I001

from typing import TYPE_CHECKING, Any

from itemloaders.processors import MapCompose, TakeFirst
from scrapy import Request, Spider
from scrapy.loader import ItemLoader

from src.items import ProductItem  # ty: ignore[unresolved-import]

if TYPE_CHECKING:
    from collections.abc import Generator

    from scrapy.http.response import Response


class ProductItemLoader(ItemLoader):
    default_item_class = ProductItem
    default_output_processor = TakeFirst()
    name_in = MapCompose(str.strip)
    price_in = MapCompose(str.strip)
    description_in = MapCompose(str.strip)


class ItemLoaderSpider(Spider):
    name = 'itemloader_spider'

    def __init__(self, start_urls: list[str], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.start_urls = start_urls

    def start_requests(self) -> Generator[Request, None, None]:
        for url in self.start_urls:
            yield Request(url, callback=self.parse)

    def parse(self, response: Response) -> Generator[Request, None, None]:
        for link in response.css('a[href*="/products/"]::attr(href)').getall():
            yield response.follow(link, callback=self.parse_product)

    def parse_product(self, response: Response) -> Generator[ProductItem, None, None]:
        loader = ProductItemLoader(response=response)  # ty: ignore[invalid-argument-type]
        loader.add_value('url', response.url)
        loader.add_css('name', 'h1::text')
        loader.add_css('price', 'span.price::text')
        loader.add_css('description', 'p.description::text')
        yield loader.load_item()
