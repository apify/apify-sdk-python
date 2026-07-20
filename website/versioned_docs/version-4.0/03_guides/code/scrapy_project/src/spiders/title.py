from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

from scrapy import Request, Spider

from ..items import TitleItem

if TYPE_CHECKING:
    from collections.abc import Generator

    from scrapy.http.response import Response


class TitleSpider(Spider):
    """A spider that extracts page titles and queues links for further crawling."""

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
        """Store the start URLs and allowed domains."""
        super().__init__(*args, **kwargs)
        self.start_urls = start_urls
        self.allowed_domains = allowed_domains

    def parse(self, response: Response) -> Generator[TitleItem | Request, None, None]:
        """Yield a `TitleItem` and a `Request` for each link on the page."""
        self.logger.info('TitleSpider is parsing %s...', response)

        # Yield the title item.
        url = response.url
        title = response.css('title::text').extract_first()
        yield TitleItem(url=url, title=title)

        # Yield a request for each link.
        for link_href in response.css('a::attr("href")'):
            link_url = urljoin(response.url, link_href.get())
            if link_url.startswith(('http://', 'https://')):
                yield Request(link_url)
