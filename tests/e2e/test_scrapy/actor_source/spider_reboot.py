from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

from scrapy import Request, Spider

from apify import Actor

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Generator

    from scrapy.http.response import Response

logger = logging.getLogger(__name__)

REBOOT_LOG_MARKER = 'Rebooting the Actor run while a request is in flight'
"""Logged right before the reboot, so a test can tell the reboot happened."""

REBOOTED_KEY = 'REBOOTED'
"""Key-value store key set before the reboot, so the rebooted run does not reboot again."""

CHAIN_LENGTH = 3
"""How many pages of the chain the spider follows."""


class RebootOnceMiddleware:
    """Downloader middleware that reboots the Actor once, while the first request it sees is being downloaded."""

    def __init__(self) -> None:
        self._reboot: asyncio.Future | None = None

    def process_request(self, request: Request) -> None:
        if self._reboot is None:
            logger.info(f'Handing the request over to the downloader: {request.url}')
            self._reboot = asyncio.ensure_future(self._reboot_once())

    async def _reboot_once(self) -> None:
        if await Actor.get_value(REBOOTED_KEY):
            return

        await Actor.set_value(REBOOTED_KEY, value=True)
        logger.info(REBOOT_LOG_MARKER)
        # The scheduler's migration listener first waits for the request in flight to finish, which takes a while.
        await Actor.reboot(event_listeners_timeout=timedelta(seconds=30))


class RebootSpider(Spider):
    """Follow a short chain of slow pages, rebooting the Actor while the first one is being downloaded."""

    name = 'reboot_spider'

    custom_settings = {  # noqa: RUF012
        'DOWNLOADER_MIDDLEWARES': {'src.spiders.spider.RebootOnceMiddleware': 543},
        'CONCURRENT_REQUESTS': 1,
    }

    def __init__(self, start_urls: list[str], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.start_urls = start_urls

    async def start(self) -> AsyncIterator[Request]:
        # Plain requests without `dont_filter`, so the rebooted run does not crawl the first page again.
        for url in self.start_urls:
            yield Request(urljoin(url, '/delayed/1'), callback=self.parse)

    def parse(self, response: Response) -> Generator[dict | Request, None, None]:
        yield {'url': response.url}
        if int(response.url.rsplit('/', 1)[-1]) < CHAIN_LENGTH:
            for href in response.css('a::attr("href")').getall():
                yield Request(urljoin(response.url, href), callback=self.parse)
