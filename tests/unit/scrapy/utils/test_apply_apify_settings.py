from __future__ import annotations

from scrapy.settings import Settings

from apify.scrapy.utils import apply_apify_settings


def test__apply_apify_settings__overrides_scheduler() -> None:
    settings = Settings()
    new_settings = apply_apify_settings(settings=settings)

    assert new_settings.get('SCHEDULER') == 'apify.scrapy.scheduler.ApifyScheduler'


def test__apply_apify_settings__update_item_pipelines() -> None:
    settings = Settings(
        {
            'ITEM_PIPELINES': {
                'scrapy.pipelines.files.FilesPipeline': 1,
            }
        }
    )
    new_settings = apply_apify_settings(settings=settings)

    assert new_settings.get('ITEM_PIPELINES') == {
        'scrapy.pipelines.files.FilesPipeline': 1,
        'apify.scrapy.pipelines.ActorDatasetPushPipeline': 1000,
    }


def test__apply_apify_settings__update_downloader_middlewares() -> None:
    settings = Settings(
        {
            'DOWNLOADER_MIDDLEWARES': {
                'scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware': 123,
                'scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware': 234,
                'scrapy.downloadermiddlewares.retry.RetryMiddleware': 345,
                'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': 543,
            },
        }
    )
    new_settings = apply_apify_settings(settings=settings)

    assert new_settings.get('DOWNLOADER_MIDDLEWARES') == {
        'scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware': None,
        'scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware': None,
        'scrapy.downloadermiddlewares.retry.RetryMiddleware': None,
        'apify.scrapy.middlewares.ApifyHttpProxyMiddleware': 950,
        'apify.scrapy.middlewares.ApifyRetryMiddleware': 1000,
        'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': 543,
    }


def test__apply_apify_settings__add_proxy_config() -> None:
    settings = Settings()
    new_settings = apply_apify_settings(settings=settings)
    assert new_settings.get('APIFY_PROXY_SETTINGS') is None

    settings = Settings()
    proxy_config = {'useApifyProxy': True, 'apifyProxyGroups': []}
    new_settings = apply_apify_settings(settings=settings, proxy_config=proxy_config)
    assert new_settings.get('APIFY_PROXY_SETTINGS') == {'useApifyProxy': True, 'apifyProxyGroups': []}
