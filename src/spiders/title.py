from __future__ import annotations

from scrapy import Spider as BaseSpider
from scrapy.http import Response


class TitleSpider(BaseSpider):
    name = 'title'
    start_urls = ['https://httpbin.org/redirect-to?url=https%3A%2F%2Fhonzajavorek.cz%2F']

    def parse(self, response: Response) -> dict[str, str]:
        return {'url': response.url}


#
