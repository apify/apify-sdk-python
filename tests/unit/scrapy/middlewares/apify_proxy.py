from __future__ import annotations

from unittest.mock import Mock

import pytest
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured

from apify.scrapy.middlewares import ApifyHttpProxyMiddleware


@pytest.fixture()
def crawler() -> Crawler:
    """
    Fixture to create a mock Scrapy Crawler object.
    """
    crawler = Mock(spec=Crawler)
    crawler.settings = Mock()
    return crawler


@pytest.mark.parametrize(
    'valid_settings',
    [
        {'APIFY_PROXY_SETTINGS': {'useApifyProxy': True}},
        {'APIFY_PROXY_SETTINGS': {'useApifyProxy': True, 'apifyProxyGroups': []}},
    ],
)
def test_from_crawler_with_valid_settings(
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
def test_from_crawler_with_invalid_settings(
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
