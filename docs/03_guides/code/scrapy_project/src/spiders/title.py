from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

from scrapy import Request, Spider

from ..items import TitleItem

if TYPE_CHECKING:
    from collections.abc import Generator

    from scrapy.http.response import Response


class TitleSpider(Spider):
    """A spider that scrapes web pages to extract titles and discover new links.

    This spider retrieves the content of the <title> element from each page and queues
    any valid hyperlinks for further crawling.
    """

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
        """A default costructor.

        Args:
            start_urls: URLs to start the scraping from.
            allowed_domains: Domains that the scraper is allowed to crawl.
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.
        """
        super().__init__(*args, **kwargs)
        self.start_urls = start_urls
        self.allowed_domains = allowed_domains

    def parse(self, response: Response) -> Generator[TitleItem | Request, None, None]:
        """Parse the web page response.

        Args:
            response: The web page response.

        Yields:
            Yields scraped `TitleItem` and new `Request` objects for links.
        """
        self.logger.info('TitleSpider is parsing %s...', response)

        # Extract and yield the TitleItem
        url = response.url
        title = response.css('title::text').extract_first()
        yield TitleItem(url=url, title=title)

        # Extract all links from the page, create `Request` objects out of them,
        # and yield them.
        for link_href in response.css('a::attr("href")'):
            link_url = urljoin(response.url, link_href.get())
            if link_url.startswith(('http://', 'https://')):
                yield Request(link_url)
