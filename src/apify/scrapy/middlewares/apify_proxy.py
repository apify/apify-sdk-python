from __future__ import annotations

from base64 import b64encode
from typing import TYPE_CHECKING
from urllib.parse import ParseResult, unquote, urlparse

from scrapy.core.downloader.handlers.http11 import TunnelError
from scrapy.exceptions import NotConfigured
from scrapy.utils.python import to_bytes

from apify import Actor, ProxyConfiguration

if TYPE_CHECKING:
    from scrapy import Request, Spider
    from scrapy.crawler import Crawler


class ApifyHttpProxyMiddleware:
    """Apify HTTP proxy middleware for Scrapy.

    This middleware enhances request processing by adding a 'proxy' field to the request's meta and an
    authentication header. It draws inspiration from the Scrapy default `HttpProxyMiddleware`. The proxy URL is
    sourced from the settings under the `APIFY_PROXY_SETTINGS` key. The value of this key, a dictionary, should be
    provided by the Actor input. An example of the proxy settings:

    proxy_settings = {'useApifyProxy': true, 'apifyProxyGroups': []}
    """

    def __init__(
        self: ApifyHttpProxyMiddleware,
        proxy_settings: dict,
        auth_encoding: str = 'latin-1',
    ) -> None:
        """Create a new instance.

        Args:
            proxy_settings: Dictionary containing proxy settings, provided by the Actor input.
            auth_encoding: Encoding for basic authentication (default is 'latin-1').
        """
        self._proxy_settings = proxy_settings
        self._auth_encoding = auth_encoding
        self.__proxy_cfg: ProxyConfiguration | None = None

    @classmethod
    def from_crawler(cls: type[ApifyHttpProxyMiddleware], crawler: Crawler) -> ApifyHttpProxyMiddleware:
        """Create an instance of ApifyHttpProxyMiddleware from a Scrapy Crawler.

        Args:
            cls: Class type.
            crawler: Scrapy Crawler object.

        Returns:
            ApifyHttpProxyMiddleware: Instance of the class.
        """
        proxy_settings = crawler.settings.get('APIFY_PROXY_SETTINGS')

        if proxy_settings is None:
            Actor.log.warning('Field "APIFY_PROXY_SETTINGS" is missing in the settings. ApifyHttpProxyMiddleware is not configured.')
            raise NotConfigured

        return cls(proxy_settings)

    @property
    async def _proxy_cfg(self: ApifyHttpProxyMiddleware) -> ProxyConfiguration:
        """Get the proxy configuration, creating it if necessary.

        Returns:
            ProxyConfiguration: Instance of the proxy configuration.

        Raises:
            NotConfigured: If creation of the proxy configuration fails.
        """
        if self.__proxy_cfg is not None:
            return self.__proxy_cfg

        proxy_cfg = await Actor.create_proxy_configuration(actor_proxy_input=self._proxy_settings)

        if proxy_cfg is None:
            Actor.log.error('Creation of proxy configuration failed')
            raise NotConfigured

        self.__proxy_cfg = proxy_cfg
        return self.__proxy_cfg

    async def process_request(self: ApifyHttpProxyMiddleware, request: Request, spider: Spider) -> None:
        """Process a Scrapy request by assigning a new proxy.

        Args:
            request: Scrapy Request object.
            spider: Scrapy Spider object.

        Raises:
            ValueError: If username and password are not provided in the proxy URL.

        Returns:
            None: The request is processed and middleware pipeline can continue.
        """
        Actor.log.debug(f'ApifyHttpProxyMiddleware.process_request: request={request}, spider={spider}')
        url = await self._get_new_proxy_url()

        if not (url.username and url.password):
            raise ValueError('Username and password must be provided in the proxy URL.')

        request.meta['proxy'] = url.geturl()
        basic_auth_header = self._get_basic_auth_header(url.username, url.password)
        request.headers[b'Proxy-Authorization'] = basic_auth_header

        Actor.log.debug(f'ApifyHttpProxyMiddleware.process_request: updated request.meta={request.meta}')

    def process_exception(
        self: ApifyHttpProxyMiddleware,
        request: Request,
        exception: Exception,
        spider: Spider,
    ) -> None | Request:
        """Process an exception that occurs during request processing.

        Args:
            request: Scrapy Request object.
            exception: Exception object.
            spider: Scrapy Spider object.

        Returns:
            If a TunnelError occurs, return the request object to halt its processing in the middleware pipeline.
            Return None otherwise to allow the continuation of request processing.
        """
        Actor.log.debug(f'ApifyHttpProxyMiddleware.process_exception: request={request}, exception={exception}, spider={spider}')

        if isinstance(exception, TunnelError):
            Actor.log.warning(f'ApifyHttpProxyMiddleware: TunnelError occurred for request="{request}", reason="{exception}", skipping...')
            return request

        return None

    async def _get_new_proxy_url(self: ApifyHttpProxyMiddleware) -> ParseResult:
        """Get a new proxy URL from the Apify proxy configuration."""
        proxy_cfg = await self._proxy_cfg
        new_url = await proxy_cfg.new_url()
        return urlparse(new_url)

    def _get_basic_auth_header(self: ApifyHttpProxyMiddleware, username: str, password: str) -> bytes:
        """Generate a basic authentication header for the given username and password."""
        string = f'{unquote(username)}:{unquote(password)}'
        user_pass = to_bytes(string, encoding=self._auth_encoding)
        return b'Basic ' + b64encode(user_pass)
