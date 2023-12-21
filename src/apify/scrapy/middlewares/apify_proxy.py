from __future__ import annotations

import base64
from typing import TYPE_CHECKING
from urllib.parse import unquote

from scrapy.exceptions import NotConfigured
from scrapy.utils.python import to_bytes

from apify import Actor

if TYPE_CHECKING:
    from scrapy import Request, Spider
    from scrapy.crawler import Crawler


class ApifyHttpProxyMiddleware:
    def __init__(self: ApifyHttpProxyMiddleware, proxy_settings: dict, auth_encoding: str = 'latin-1') -> None:
        self.auth_encoding = auth_encoding
        self.proxy_settings = proxy_settings

    @classmethod
    def from_crawler(cls: type[ApifyHttpProxyMiddleware], crawler: Crawler) -> ApifyHttpProxyMiddleware:
        proxy_settings = crawler.settings.get('PROXY_SETTINGS')

        if not proxy_settings:
            Actor.log.warning('Field "PROXY_SETTINGS" is missing in the settings. ApifyHttpProxyMiddleware is not NotConfigured.')
            raise NotConfigured

        return cls(proxy_settings)

    def process_request(self: ApifyHttpProxyMiddleware, request: Request, spider: Spider) -> None:
        if self.proxy_settings:
            request.meta['proxy'] = self.proxy_settings['url']
            creds = self._basic_auth_header()
            request.headers[b'Proxy-Authorization'] = b'Basic ' + creds

        Actor.log.info(f'ApifyHttpProxyMiddleware: request.meta={request.meta}')

    def _basic_auth_header(self: ApifyHttpProxyMiddleware) -> bytes:
        username = self.proxy_settings['username']
        password = self.proxy_settings['password']
        user_pass = to_bytes(f'{unquote(username)}:{unquote(password)}', encoding=self.auth_encoding)
        return base64.b64encode(user_pass)
