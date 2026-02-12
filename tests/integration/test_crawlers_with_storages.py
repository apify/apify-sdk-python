from __future__ import annotations

import re
from typing import TYPE_CHECKING

from apify_shared.consts import ApifyEnvVars
from crawlee import ConcurrencySettings
from crawlee.crawlers import ParselCrawler, ParselCrawlingContext

from apify import Actor

if TYPE_CHECKING:
    import pytest
    from pytest_httpserver import HTTPServer

    from crawlee._types import BasicCrawlingContext


async def test_max_crawl_depth(
    apify_token: str,
    monkeypatch: pytest.MonkeyPatch,
    httpserver: HTTPServer,
) -> None:
    """Test that the crawler respects max_crawl_depth."""
    httpserver.expect_request('/').respond_with_data(
        '<html><body><a href="/2">Link</a></body></html>',
        content_type='text/html',
    )
    httpserver.expect_request('/2').respond_with_data(
        '<html><body><a href="/22">Link</a></body></html>',
        content_type='text/html',
    )
    httpserver.expect_request('/22').respond_with_data(
        '<html><body><a href="/222">Link</a></body></html>',
        content_type='text/html',
    )
    httpserver.expect_request('/222').respond_with_data(
        '<html><body>End</body></html>',
        content_type='text/html',
    )

    base_url = httpserver.url_for('/')
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_token)

    async with Actor:
        crawler = ParselCrawler(max_crawl_depth=2)
        finished: list[str] = []
        enqueue_pattern = re.compile(re.escape(base_url.rstrip('/')) + r'/2+$')

        @crawler.router.default_handler
        async def default_handler(context: ParselCrawlingContext) -> None:
            await context.enqueue_links(include=[enqueue_pattern])
            finished.append(context.request.url)

        await crawler.run([base_url])
        assert finished == [base_url, f'{base_url.rstrip("/")}/2', f'{base_url.rstrip("/")}/22']


async def test_max_requests_per_crawl(
    apify_token: str,
    monkeypatch: pytest.MonkeyPatch,
    httpserver: HTTPServer,
) -> None:
    """Test that the crawler respects max_requests_per_crawl."""
    for i in range(10):
        links = ''.join(f'<a href="/{j}">Link {j}</a>' for j in range(i + 1, min(i + 3, 10)))
        httpserver.expect_request(f'/{i}').respond_with_data(
            f'<html><body>{links}</body></html>',
            content_type='text/html',
        )
    httpserver.expect_request('/').respond_with_data(
        '<html><body><a href="/0">Link 0</a><a href="/1">Link 1</a></body></html>',
        content_type='text/html',
    )

    base_url = httpserver.url_for('/')
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_token)

    async with Actor:
        crawler = ParselCrawler(
            max_requests_per_crawl=3,
            concurrency_settings=ConcurrencySettings(max_concurrency=1, desired_concurrency=1),
        )
        finished: list[str] = []

        @crawler.router.default_handler
        async def default_handler(context: ParselCrawlingContext) -> None:
            await context.enqueue_links()
            finished.append(context.request.url)

        await crawler.run([base_url])
        assert len(finished) == 3


async def test_max_request_retries(
    apify_token: str,
    monkeypatch: pytest.MonkeyPatch,
    httpserver: HTTPServer,
) -> None:
    """Test that the crawler respects max_request_retries."""
    httpserver.expect_request('/').respond_with_data(
        '<html><body>OK</body></html>',
        content_type='text/html',
    )

    base_url = httpserver.url_for('/')
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_token)

    async with Actor:
        max_retries = 3
        crawler = ParselCrawler(max_request_retries=max_retries)
        failed_counter = 0

        @crawler.error_handler
        async def error_handler(_: BasicCrawlingContext, __: Exception) -> None:
            nonlocal failed_counter
            failed_counter += 1

        @crawler.router.default_handler
        async def default_handler(_: ParselCrawlingContext) -> None:
            raise RuntimeError('Some error')

        await crawler.run([base_url])
        assert failed_counter == max_retries
