from __future__ import annotations

import pytest
from scrapy import Request, Spider
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured

from apify.scrapy.middlewares import ApifyHttpProxyMiddleware


class DummySpider(Spider):
    name = 'dummy_spider'


@pytest.fixture()
def crawler(monkeypatch: pytest.MonkeyPatch) -> Crawler:
    """
    Fixture to create a mock Scrapy Crawler object.
    """
    crawler = Crawler(DummySpider)
    monkeypatch.setattr(crawler, 'settings', {})
    return crawler


@pytest.fixture()
def middleware() -> ApifyHttpProxyMiddleware:
    """
    Fixture to create a Apify HTTP proxy middleware.
    """
    proxy_settings = {'useApifyProxy': True}
    return ApifyHttpProxyMiddleware(proxy_settings)


@pytest.mark.parametrize(
    'valid_settings',
    [
        {'APIFY_PROXY_SETTINGS': {'useApifyProxy': True}},
        {'APIFY_PROXY_SETTINGS': {'useApifyProxy': True, 'apifyProxyGroups': []}},
    ],
)
def test__from_crawler__valid_settings(
    crawler: Crawler,
    monkeypatch: pytest.MonkeyPatch,
    valid_settings: dict,
) -> None:
    """
    Test the ApifyHttpProxyMiddleware.from_crawler method with valid proxy settings.
    """
    monkeypatch.setattr(crawler, 'settings', valid_settings)

    # Ensure no exceptions are raised
    middleware = ApifyHttpProxyMiddleware.from_crawler(crawler)

    # Validate that the middleware instance is created with the correct settings
    assert middleware._proxy_settings == valid_settings['APIFY_PROXY_SETTINGS']


@pytest.mark.parametrize(
    'invalid_settings',
    [
        {},
        {'a': 1},
        {'APIFY_PROXY_SETTINGS': {}},
        {'APIFY_PROXY_SETTINGS': {'useApifyProxy': None}},
        {'APIFY_PROXY_SETTINGS': {'useApifyProxy': False}},
    ],
)
def test__from_crawler__invalid_settings(
    crawler: Crawler,
    monkeypatch: pytest.MonkeyPatch,
    invalid_settings: dict,
) -> None:
    """
    Test the ApifyHttpProxyMiddleware.from_crawler method with invalid or turned off proxy settings.
    """
    monkeypatch.setattr(crawler, 'settings', invalid_settings)

    # Ensure that NotConfigured is raised when settings are invalid
    with pytest.raises(NotConfigured):
        ApifyHttpProxyMiddleware.from_crawler(crawler)


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
