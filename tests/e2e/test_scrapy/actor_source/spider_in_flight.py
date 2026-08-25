from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

from scrapy import Request, Spider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Generator

    from scrapy.http.response import Response

logger = logging.getLogger(__name__)

IN_FLIGHT_LOG_MARKER = 'Handing the request over to the downloader'
"""Logged once Scrapy starts downloading a request, so a test knows the request is in flight."""


class MarkInFlightMiddleware:
    """Downloader middleware that logs `IN_FLIGHT_LOG_MARKER` for every request it sees."""

    def process_request(self, request: Request) -> None:
        logger.info(f'{IN_FLIGHT_LOG_MARKER}: {request.url}')


class InFlightSpider(Spider):
    """Request a page that does not answer, so the request stays in flight until the run is interrupted."""

    name = 'in_flight_spider'

    custom_settings = {  # noqa: RUF012
        'DOWNLOADER_MIDDLEWARES': {'src.spiders.spider.MarkInFlightMiddleware': 543},
        # The page answers after 10 minutes; the download must not time out before the test aborts the run.
        'DOWNLOAD_TIMEOUT': 600,
    }

    def __init__(self, start_urls: list[str], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.start_urls = start_urls

    async def start(self) -> AsyncIterator[Request]:
        for url in self.start_urls:
            yield Request(urljoin(url, '/slow'), callback=self.parse)

    def parse(self, response: Response) -> Generator[dict, None, None]:
        yield {'url': response.url}
