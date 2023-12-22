from __future__ import annotations

from urllib.parse import ParseResult, urlparse

import pytest
from scrapy import Request, Spider
from scrapy.core.downloader.handlers.http11 import TunnelError
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured

from apify.scrapy.middlewares import ApifyHttpProxyMiddleware


class DummySpider(Spider):
    name = 'dummy_spider'


@pytest.fixture()
def middleware() -> ApifyHttpProxyMiddleware:
    """
    Fixture to create an Apify HTTP proxy middleware.
    """
    proxy_settings = {'useApifyProxy': True}
    return ApifyHttpProxyMiddleware(proxy_settings)


@pytest.fixture()
def crawler(monkeypatch: pytest.MonkeyPatch) -> Crawler:
    """
    Fixture to create a Scrapy crawler.
    """
    crawler = Crawler(DummySpider)
    monkeypatch.setattr(crawler, 'settings', {})
    return crawler


@pytest.fixture()
def spider() -> DummySpider:
    """
    Fixture to create a "dummy" Scrapy spider.
    """
    return DummySpider()


@pytest.fixture()
def dummy_request() -> Request:
    """
    Fixture to create a "dummy" Scrapy spider.
    """
    return Request('https://example.com')


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
)
def test__from_crawler(
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


async def test__get_new_proxy_url() -> None:
    ...


@pytest.mark.parametrize(
    ('proxy_url', 'expected_exception', 'expected_request_header'),
    [
        ('http://username:password@proxy.example.com:8080', None, b'Basic dXNlcm5hbWU6cGFzc3dvcmQ='),
        ('http://user123:pass456@proxy.example.com:5748', None, b'Basic dXNlcjEyMzpwYXNzNDU2'),
        ('http://@proxy.example.com:2943', ValueError, b''),
    ],
)
async def test__process_request(
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
    ('exception', 'none_returned_values_is_expected'),
    [
        (TunnelError(), False),
        (ValueError(), True),
    ],
)
def test__process_exception(
    middleware: ApifyHttpProxyMiddleware,
    spider: DummySpider,
    dummy_request: Request,
    exception: Exception,
    *,
    none_returned_values_is_expected: bool,
) -> None:
    returned_value = middleware.process_exception(dummy_request, exception, spider)

    if none_returned_values_is_expected:
        assert returned_value is None

    else:
        assert returned_value == dummy_request


@pytest.mark.parametrize(
    ('username', 'password', 'expected_auth_header'),
    [
        ('username', 'password', b'Basic dXNlcm5hbWU6cGFzc3dvcmQ='),
        ('john_smith', 'secret_password_123', b'Basic am9obl9zbWl0aDpzZWNyZXRfcGFzc3dvcmRfMTIz'),
    ],
)
def test__get_basic_auth_header(
    middleware: ApifyHttpProxyMiddleware,
    username: str,
    password: str,
    expected_auth_header: bytes,
) -> None:
    auth_header = middleware._get_basic_auth_header(username, password)
    assert auth_header == expected_auth_header
