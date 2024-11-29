from __future__ import annotations

from urllib.parse import ParseResult, urlparse

import pytest
from scrapy import Request, Spider
from scrapy.core.downloader.handlers.http11 import TunnelError
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured

from apify import ProxyConfiguration
from apify.scrapy.middlewares import ApifyHttpProxyMiddleware


class DummySpider(Spider):
    name = 'dummy_spider'


@pytest.fixture
def middleware() -> ApifyHttpProxyMiddleware:
    """Fixture to create an Apify HTTP proxy middleware."""
    proxy_settings = {'useApifyProxy': True}
    return ApifyHttpProxyMiddleware(proxy_settings)


@pytest.fixture
def crawler(monkeypatch: pytest.MonkeyPatch) -> Crawler:
    """Fixture to create a Scrapy crawler."""
    crawler = Crawler(DummySpider)
    monkeypatch.setattr(crawler, 'settings', {})
    return crawler


@pytest.fixture
def spider() -> DummySpider:
    """Fixture to create a "dummy" Scrapy spider."""
    return DummySpider()


@pytest.fixture
def dummy_request() -> Request:
    """Fixture to create a "dummy" Scrapy spider."""
    return Request('https://example.com')


@pytest.fixture
def proxy_configuration() -> ProxyConfiguration:
    """Fixture to create an Apify ProxyConfiguration object."""
    return ProxyConfiguration()


@pytest.mark.parametrize(
    ('settings', 'expected_exception'),
    [
        ({'APIFY_PROXY_SETTINGS': {'useApifyProxy': True}}, None),
        ({'APIFY_PROXY_SETTINGS': {'useApifyProxy': True, 'apifyProxyGroups': []}}, None),
        ({}, NotConfigured),
        ({'a': 1}, NotConfigured),
        ({'APIFY_PROXY_SETTINGS': {}}, NotConfigured),
        ({'APIFY_PROXY_SETTINGS': {'useApifyProxy': None}}, NotConfigured),
        ({'APIFY_PROXY_SETTINGS': {'useApifyProxy': False}}, NotConfigured),
    ],
    ids=[
        'valid_proxy_settings_enabled',
        'valid_proxy_settings_with_groups',
        'no_settings',
        'irrelevant_setting',
        'empty_proxy_settings',
        'use_apify_proxy_none',
        'use_apify_proxy_false',
    ],
)
def test_initialization_from_crawler(
    crawler: Crawler,
    monkeypatch: pytest.MonkeyPatch,
    settings: dict,
    expected_exception: type[Exception] | None,
) -> None:
    monkeypatch.setattr(crawler, 'settings', settings)

    if expected_exception is None:
        middleware = ApifyHttpProxyMiddleware.from_crawler(crawler)
        assert middleware._proxy_settings == settings['APIFY_PROXY_SETTINGS']

    else:
        with pytest.raises(expected_exception):
            ApifyHttpProxyMiddleware.from_crawler(crawler)


@pytest.mark.parametrize(
    'expected_proxy_url',
    ['http://username:password@proxy.example.com:8080', 'http://hsdfgds:52354325@proxy.apify.com:5748'],
    ids=['example_proxy', 'apify_proxy'],
)
async def test_retrieves_new_proxy_url(
    monkeypatch: pytest.MonkeyPatch,
    middleware: ApifyHttpProxyMiddleware,
    proxy_configuration: ProxyConfiguration,
    expected_proxy_url: str,
) -> None:
    async def mock_new_url() -> str:
        return expected_proxy_url

    monkeypatch.setattr(proxy_configuration, 'new_url', mock_new_url)
    middleware._proxy_cfg_internal = proxy_configuration
    proxy_url = await middleware._get_new_proxy_url()
    assert proxy_url == urlparse(expected_proxy_url)


@pytest.mark.parametrize(
    ('proxy_url', 'expected_exception', 'expected_request_header'),
    [
        ('http://username:password@proxy.example.com:8080', None, b'Basic dXNlcm5hbWU6cGFzc3dvcmQ='),
        ('http://user123:pass456@proxy.apify.com:5748', None, b'Basic dXNlcjEyMzpwYXNzNDU2'),
        ('http://@proxy.example.com:2943', ValueError, b''),
    ],
    ids=['valid_example_proxy', 'valid_apify_proxy', 'invalid_proxy_missing_credentials'],
)
async def test_process_request_with_proxy(
    monkeypatch: pytest.MonkeyPatch,
    middleware: ApifyHttpProxyMiddleware,
    spider: DummySpider,
    dummy_request: Request,
    proxy_url: str,
    expected_exception: type[Exception] | None,
    expected_request_header: bytes,
) -> None:
    async def mock_get_new_proxy_url() -> ParseResult:
        return urlparse(proxy_url)

    monkeypatch.setattr(middleware, '_get_new_proxy_url', mock_get_new_proxy_url)

    if expected_exception is None:
        await middleware.process_request(dummy_request, spider)
        assert dummy_request.meta['proxy'] == proxy_url
        assert dummy_request.headers[b'Proxy-Authorization'] == expected_request_header
    else:
        with pytest.raises(expected_exception):
            await middleware.process_request(dummy_request, spider)


@pytest.mark.parametrize(
    'exception',
    [TunnelError(), ValueError()],
    ids=['tunnel_error', 'value_error'],
)
def test_handles_exceptions(
    middleware: ApifyHttpProxyMiddleware,
    spider: DummySpider,
    dummy_request: Request,
    exception: Exception,
) -> None:
    returned_value = middleware.process_exception(dummy_request, exception, spider)  # type: ignore[func-returns-value]
    assert returned_value is None
