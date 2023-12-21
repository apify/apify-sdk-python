from __future__ import annotations

from unittest.mock import Mock

import pytest
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.settings import Settings

from apify.scrapy.middlewares import ApifyHttpProxyMiddleware


@pytest.fixture()
def crawler() -> Crawler:
    crawler = Mock(spec=Crawler)
    crawler.settings = Mock(spec=Settings)
    return crawler


@pytest.mark.parametrize(
    'valid_settings',
    [
        {'APIFY_PROXY_SETTINGS': {'useApifyProxy': True}},
        {'APIFY_PROXY_SETTINGS': {'useApifyProxy': True, 'apifyProxyGroups': []}},
    ],
)
def test_from_crawler_with_valid_settings(crawler: Crawler, valid_settings: dict) -> None:
    crawler.settings.get.return_value = valid_settings

    print(crawler)

    # Ensure no exceptions are raised
    middleware = ApifyHttpProxyMiddleware.from_crawler(crawler)

    # Validate that the middleware instance is created with the correct settings
    assert middleware._proxy_settings == valid_settings['APIFY_PROXY_SETTINGS']


@pytest.mark.parametrize(
    'invalid_settings',
    [
        None,
        {},
        {'APIFY_PROXY_SETTINGS': {}},
        {'APIFY_PROXY_SETTINGS': {'useApifyProxy': False}},
    ],
)
def test_from_crawler_with_invalid_settings(crawler: Crawler, invalid_settings: dict | None) -> None:
    """Test invalid or turn off proxy settings."""
    crawler.settings.get.return_value = invalid_settings

    # Ensure that NotConfigured is raised when settings are missing
    with pytest.raises(NotConfigured):
        ApifyHttpProxyMiddleware.from_crawler(crawler)
