from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

from scrapy import Request, Spider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Generator

    from scrapy.http.response import Response


class RedirectSpider(Spider):
    """Fetch a page that redirects and report where the redirect landed."""

    name = 'redirect_spider'

    def __init__(self, start_urls: list[str], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.start_urls = start_urls

    async def start(self) -> AsyncIterator[Request]:
        # Plain requests without `dont_filter`, so the redirected request goes through deduplication.
        for url in self.start_urls:
            yield Request(urljoin(url, '/redirect'), callback=self.parse)

    def parse(self, response: Response) -> Generator[dict, None, None]:
        yield {
            'url': response.url,
            'title': response.css('title::text').get(''),
        }
