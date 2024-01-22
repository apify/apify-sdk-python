from __future__ import annotations

from dataclasses import dataclass

import pytest
from scrapy.settings import Settings

from apify.scrapy.utils import apply_apify_settings


@dataclass(frozen=True)
class TestCase:
    settings: Settings
    proxy_config: dict | None
    expected_output: Settings


test_cases = [
    # Test case with default settings and no proxy configuration
    TestCase(
        settings=Settings(),
        proxy_config=None,
        expected_output=Settings(
            {
                'SCHEDULER': 'apify.scrapy.scheduler.ApifyScheduler',
                'ITEM_PIPELINES': {
                    'apify.scrapy.pipelines.ActorDatasetPushPipeline': 1000,
                },
                'DOWNLOADER_MIDDLEWARES': {
                    'scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware': None,
                    'scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware': None,
                    'scrapy.downloadermiddlewares.retry.RetryMiddleware': None,
                    'apify.scrapy.middlewares.ApifyHttpProxyMiddleware': 950,
                    'apify.scrapy.middlewares.ApifyRetryMiddleware': 1000,
                },
                'APIFY_PROXY_SETTINGS': None,
            }
        ),
    ),
    # Test case with default settings and proxy configuration
    TestCase(
        settings=Settings(),
        proxy_config={'useApifyProxy': True, 'apifyProxyGroups': []},
        expected_output=Settings(
            {
                'SCHEDULER': 'apify.scrapy.scheduler.ApifyScheduler',
                'ITEM_PIPELINES': {
                    'apify.scrapy.pipelines.ActorDatasetPushPipeline': 1000,
                },
                'DOWNLOADER_MIDDLEWARES': {
                    'scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware': None,
                    'scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware': None,
                    'scrapy.downloadermiddlewares.retry.RetryMiddleware': None,
                    'apify.scrapy.middlewares.ApifyHttpProxyMiddleware': 950,
                    'apify.scrapy.middlewares.ApifyRetryMiddleware': 1000,
                },
                'APIFY_PROXY_SETTINGS': {'useApifyProxy': True, 'apifyProxyGroups': []},
            }
        ),
    ),
    # Test case with custom settings and proxy configuration
    TestCase(
        settings=Settings(
            {
                'SCHEDULER': 'scrapy.core.scheduler.Scheduler',
                'ITEM_PIPELINES': {
                    'scrapy.pipelines.files.FilesPipeline': 1,
                },
                'DOWNLOADER_MIDDLEWARES': {
                    'scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware': 123,
                    'scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware': 234,
                    'scrapy.downloadermiddlewares.retry.RetryMiddleware': 345,
                    'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': 543,
                },
            }
        ),
        proxy_config={'useApifyProxy': True, 'apifyProxyGroups': []},
        expected_output=Settings(
            {
                'SCHEDULER': 'apify.scrapy.scheduler.ApifyScheduler',
                'ITEM_PIPELINES': {
                    'scrapy.pipelines.files.FilesPipeline': 1,
                    'apify.scrapy.pipelines.ActorDatasetPushPipeline': 1000,
                },
                'DOWNLOADER_MIDDLEWARES': {
                    'scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware': None,
                    'scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware': None,
                    'scrapy.downloadermiddlewares.retry.RetryMiddleware': None,
                    'apify.scrapy.middlewares.ApifyHttpProxyMiddleware': 950,
                    'apify.scrapy.middlewares.ApifyRetryMiddleware': 1000,
                    'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': 543,
                },
                'APIFY_PROXY_SETTINGS': {'useApifyProxy': True, 'apifyProxyGroups': []},
            }
        ),
    ),
]


@pytest.mark.parametrize('tc', test_cases)
@pytest.mark.only()
def test_apply_apify_settings(tc: TestCase) -> None:
    output_settings = apply_apify_settings(settings=tc.settings, proxy_config=tc.proxy_config)
    print(dict(output_settings))

    assert output_settings['SCHEDULER'] == tc.expected_output['SCHEDULER']
    assert output_settings['ITEM_PIPELINES'] == tc.expected_output['ITEM_PIPELINES']
    assert output_settings['DOWNLOADER_MIDDLEWARES'] == tc.expected_output['DOWNLOADER_MIDDLEWARES']
    assert output_settings['APIFY_PROXY_SETTINGS'] == tc.expected_output['APIFY_PROXY_SETTINGS']
