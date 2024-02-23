from __future__ import annotations

import asyncio
from base64 import b64encode
from urllib.parse import unquote

try:
    from scrapy.settings import Settings  # noqa: TCH002
    from scrapy.utils.project import get_project_settings
    from scrapy.utils.python import to_bytes
except ImportError as exc:
    raise ImportError(
        'To use this module, you need to install the "scrapy" extra. Run "pip install apify[scrapy]".',
    ) from exc

from apify.actor import Actor
from apify.storages import RequestQueue, StorageClientManager

nested_event_loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()


def get_basic_auth_header(username: str, password: str, auth_encoding: str = 'latin-1') -> bytes:
    """Generate a basic authentication header for the given username and password."""
    string = f'{unquote(username)}:{unquote(password)}'
    user_pass = to_bytes(string, encoding=auth_encoding)
    return b'Basic ' + b64encode(user_pass)


def get_running_event_loop_id() -> int:
    """Get the ID of the currently running event loop.

    It could be useful mainly for debugging purposes.

    Returns:
        The ID of the event loop.
    """
    return id(asyncio.get_running_loop())


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

    # Disable the default AjaxCrawlMiddleware since it can be problematic with Apify. It can return a new request
    # during process_response, but currently we have no way of detecting it and handling it properly.
    settings['DOWNLOADER_MIDDLEWARES']['scrapy.downloadermiddlewares.ajaxcrawl.AjaxCrawlMiddleware'] = None

    # Replace the default HttpProxyMiddleware with ApifyHttpProxyMiddleware
    settings['DOWNLOADER_MIDDLEWARES']['scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware'] = None
    settings['DOWNLOADER_MIDDLEWARES']['apify.scrapy.middlewares.ApifyHttpProxyMiddleware'] = 750

    # Store the proxy configuration
    settings['APIFY_PROXY_SETTINGS'] = proxy_config

    return settings


async def open_queue_with_custom_client() -> RequestQueue:
    """Open a Request Queue with custom Apify Client.

    TODO: add support for custom client to Actor.open_request_queue(), so that
    we don't have to do this hacky workaround
    """
    # Create a new Apify Client with its httpx client in the custom event loop
    custom_loop_apify_client = Actor.new_client()

    # Set the new Apify Client as the default client, back up the old client
    old_client = Actor.apify_client
    StorageClientManager.set_cloud_client(custom_loop_apify_client)

    # Create a new Request Queue in the custom event loop,
    # replace its Apify client with the custom loop's Apify client
    rq = await Actor.open_request_queue()

    if Actor.config.is_at_home:
        rq._request_queue_client = custom_loop_apify_client.request_queue(
            rq._id,
            client_key=rq._client_key,
        )

    # Restore the old Apify Client as the default client
    StorageClientManager.set_cloud_client(old_client)
    return rq
