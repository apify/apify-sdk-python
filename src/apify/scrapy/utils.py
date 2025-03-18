from __future__ import annotations

from base64 import b64encode
from typing import TYPE_CHECKING
from urllib.parse import unquote

from scrapy.utils.project import get_project_settings
from scrapy.utils.python import to_bytes

if TYPE_CHECKING:
    from scrapy.settings import Settings


def get_basic_auth_header(username: str, password: str, auth_encoding: str = 'latin-1') -> bytes:
    """Generate a basic authentication header for the given username and password."""
    string = f'{unquote(username)}:{unquote(password)}'
    user_pass = to_bytes(string, encoding=auth_encoding)
    return b'Basic ' + b64encode(user_pass)


def apply_apify_settings(*, settings: Settings | None = None, proxy_config: dict | None = None) -> Settings:
    """Integrates Apify configuration into a Scrapy project settings.

    Note: The function directly modifies the passed `settings` object and also returns it.

    Args:
        settings: Scrapy project settings to be modified.
        proxy_config: Proxy configuration to be stored in the settings.

    Returns:
        Scrapy project settings with custom configurations.
    """
    if settings is None:
        settings = get_project_settings()

    # Use ApifyScheduler as the scheduler
    settings['SCHEDULER'] = 'apify.scrapy.scheduler.ApifyScheduler'

    # Add the ActorDatasetPushPipeline into the item pipelines, assigning it the highest integer (1000),
    # ensuring it is executed as the final step in the pipeline sequence
    settings['ITEM_PIPELINES']['apify.scrapy.pipelines.ActorDatasetPushPipeline'] = 1000

    # Replace the default HttpProxyMiddleware with ApifyHttpProxyMiddleware
    settings['DOWNLOADER_MIDDLEWARES']['scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware'] = None
    settings['DOWNLOADER_MIDDLEWARES']['apify.scrapy.middlewares.ApifyHttpProxyMiddleware'] = 750

    # Set the default HTTPCache middleware storage backend to ApifyCacheStorage
    settings['HTTPCACHE_STORAGE'] = 'apify.scrapy.extensions.ApifyCacheStorage'

    # Store the proxy configuration
    settings['APIFY_PROXY_SETTINGS'] = proxy_config

    return settings
