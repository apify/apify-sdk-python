# ruff: noqa: TID252, RUF012

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urljoin

from scrapy import Request, Spider

from ..items import TitleItem

if TYPE_CHECKING:
    from collections.abc import Generator

    from scrapy.responsetypes import Response


class TitleSpider(Spider):
    """Scrapes title pages and enqueues all links found on the page."""

    name = 'title_spider'

    # The `start_urls` specified in this class will be merged with the `start_urls` value from your Actor input
    # when the project is executed using Apify.
    start_urls = ['https://apify.com/']

    # Scrape only the pages within the Apify domain.
    allowed_domains = ['apify.com']

    # Limit the number of pages to scrape.
    custom_settings = {'CLOSESPIDER_PAGECOUNT': 10}

    def parse(self, response: Response) -> Generator[TitleItem | Request, None, None]:
        """Parse the web page response.

        Args:
            response: The web page response.

        Yields:
            Yields scraped TitleItem and Requests for links.
        """
        self.logger.info('TitleSpider is parsing %s...', response)

        # Extract and yield the TitleItem
        url = response.url
        title = response.css('title::text').extract_first()
        yield TitleItem(url=url, title=title)

        # Extract all links from the page, create Requests out of them, and yield them
        for link_href in response.css('a::attr("href")'):
            link_url = urljoin(response.url, link_href.get())
            if link_url.startswith(('http://', 'https://')):
                yield Request(link_url)
