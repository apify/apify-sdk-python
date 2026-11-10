from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from urllib.parse import ParseResult, urlparse

from scrapy.core.downloader.handlers.http11 import TunnelError
from scrapy.exceptions import NotConfigured

from apify import Actor, ProxyConfiguration
from apify.scrapy.utils import get_basic_auth_header

if TYPE_CHECKING:
    from scrapy import Request
    from scrapy.crawler import Crawler


class ApifyHttpProxyMiddleware:
    """Apify HTTP proxy middleware for Scrapy.

    This middleware enhances request processing by adding a 'proxy' field to the request's meta and an authentication
    header. It draws inspiration from the `HttpProxyMiddleware` included by default in Scrapy projects. The proxy URL
    is sourced from the settings under the `APIFY_PROXY_SETTINGS` key. The value of this key, a dictionary, should be
    provided by the Actor input. An example of the proxy settings:

    proxy_settings = {'useApifyProxy': true, 'apifyProxyGroups': []}
    """

    def __init__(self, proxy_settings: dict) -> None:
        """Create a new instance.

        Args:
            proxy_settings: Dictionary containing proxy settings, provided by the Actor input.
        """
        self._proxy_settings = proxy_settings
        self._proxy_cfg_internal: ProxyConfiguration | None = None
        self._proxy_cfg_lock = asyncio.Lock()
        self._runs_without_proxy = False

    @classmethod
    def from_crawler(cls: type[ApifyHttpProxyMiddleware], crawler: Crawler) -> ApifyHttpProxyMiddleware:
        """Create an instance of ApifyHttpProxyMiddleware from a Scrapy Crawler.

        Args:
            crawler: Scrapy Crawler object.

        Returns: Instance of the class.
        """
        proxy_settings: dict | None = crawler.settings.get('APIFY_PROXY_SETTINGS')

        if proxy_settings is None:
            Actor.log.info(
                'ApifyHttpProxyMiddleware is not going to be used. Object "proxyConfiguration" is probably missing '
                'in the Actor input.'
            )
            raise NotConfigured

        use_apify_proxy = proxy_settings.get('useApifyProxy', False)

        if use_apify_proxy is not True:
            Actor.log.info(
                'ApifyHttpProxyMiddleware is not going to be used. Actor input field '
                '"proxyConfiguration.useApifyProxy" is set to False.'
            )
            raise NotConfigured

        return cls(proxy_settings)

    async def process_request(self, request: Request) -> None:
        """Process a Scrapy request by assigning a new proxy.

        In a local run that cannot use Apify Proxy, the request is left without a proxy.

        Args:
            request: Scrapy Request object.

        Raises:
            ValueError: If username and password are not provided in the proxy URL.
        """
        url = await self._get_new_proxy_url()

        if url is None:
            return

        if not (url.username and url.password):
            raise ValueError('Username and password must be provided in the proxy URL.')

        request.meta['proxy'] = url.geturl()
        basic_auth_header = get_basic_auth_header(url.username, url.password)
        request.headers[b'Proxy-Authorization'] = basic_auth_header

    def process_exception(
        self,
        request: Request,
        exception: Exception,
    ) -> None:
        """Process an exception that occurs during request processing.

        Args:
            request: Scrapy Request object.
            exception: Exception object.

        Returns:
            Returning None, meaning Scrapy will continue processing this exception, executing any other
            process_exception() methods of installed middleware, until no middleware is left and the default
            exception handling kicks in.
        """
        if isinstance(exception, TunnelError):
            Actor.log.warning(
                'ApifyHttpProxyMiddleware: TunnelError occurred for request="%s", reason="%s", skipping...',
                request,
                exception,
            )

    async def _get_new_proxy_url(self) -> ParseResult | None:
        """Get a new proxy URL.

        Returns: New proxy URL, or None when the run goes without a proxy.
        """
        # The lock makes concurrent first requests create the proxy configuration only once.
        async with self._proxy_cfg_lock:
            if self._proxy_cfg_internal is None and not self._runs_without_proxy:
                self._proxy_cfg_internal = await Actor.create_proxy_configuration(
                    actor_proxy_input=self._proxy_settings
                )
                # `from_crawler` guarantees `useApifyProxy` is set, so None only comes from a local run that cannot
                # use Apify Proxy. `ProxyConfiguration.initialize` has already logged a warning about it.
                self._runs_without_proxy = self._proxy_cfg_internal is None

        if self._proxy_cfg_internal is None:
            return None

        new_url = await self._proxy_cfg_internal.new_url()
        return urlparse(new_url) if new_url else None
