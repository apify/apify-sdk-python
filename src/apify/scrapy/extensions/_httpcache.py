from __future__ import annotations

import gzip
import io
import pickle
import re
import struct
from logging import getLogger
from time import time
from typing import TYPE_CHECKING

from scrapy.http.headers import Headers
from scrapy.responsetypes import responsetypes

from apify import Configuration
from apify.apify_storage_client import ApifyStorageClient
from apify.scrapy._async_thread import AsyncThread
from apify.storages import KeyValueStore

if TYPE_CHECKING:
    from scrapy import Request, Spider
    from scrapy.http.response import Response
    from scrapy.settings import BaseSettings
    from scrapy.utils.request import RequestFingerprinterProtocol

logger = getLogger(__name__)


class ApifyCacheStorage:
    """A Scrapy cache storage that uses the Apify `KeyValueStore` to store responses.

    It can be set as a storage for Scrapy's built-in `HttpCacheMiddleware`, which caches
    responses to requests. See HTTPCache middleware settings (prefixed with `HTTPCACHE_`)
    in the Scrapy documentation for more information. Requires the asyncio Twisted reactor
    to be installed.
    """

    def __init__(self, settings: BaseSettings) -> None:
        self._expiration_max_items = 100
        self._expiration_secs: int = settings.getint('HTTPCACHE_EXPIRATION_SECS')
        self._spider: Spider | None = None
        self._kvs: KeyValueStore | None = None
        self._fingerprinter: RequestFingerprinterProtocol | None = None
        self._async_thread: AsyncThread | None = None

    def open_spider(self, spider: Spider) -> None:
        """Open the cache storage for a spider."""
        logger.debug('Using Apify key value cache storage', extra={'spider': spider})
        self._spider = spider
        self._fingerprinter = spider.crawler.request_fingerprinter
        kvs_name = get_kvs_name(spider.name)

        async def open_kvs() -> KeyValueStore:
            config = Configuration.get_global_configuration()
            if config.is_at_home:
                storage_client = ApifyStorageClient.from_config(config)
                return await KeyValueStore.open(name=kvs_name, storage_client=storage_client)
            return await KeyValueStore.open(name=kvs_name)

        logger.debug("Starting background thread for cache storage's event loop")
        self._async_thread = AsyncThread()
        logger.debug(f"Opening cache storage's {kvs_name!r} key value store")
        self._kvs = self._async_thread.run_coro(open_kvs())

    def close_spider(self, _: Spider, current_time: int | None = None) -> None:
        """Close the cache storage for a spider."""
        if self._async_thread is None:
            raise ValueError('Async thread not initialized')

        logger.info(f'Cleaning up cache items (max {self._expiration_max_items})')
        if self._expiration_secs > 0:
            if current_time is None:
                current_time = int(time())

            async def expire_kvs() -> None:
                if self._kvs is None:
                    raise ValueError('Key value store not initialized')
                i = 0
                async for item in self._kvs.iterate_keys():
                    value = await self._kvs.get_value(item.key)
                    try:
                        gzip_time = read_gzip_time(value)
                    except Exception as e:
                        logger.warning(f'Malformed cache item {item.key}: {e}')
                        await self._kvs.set_value(item.key, None)
                    else:
                        if self._expiration_secs < current_time - gzip_time:
                            logger.debug(f'Expired cache item {item.key}')
                            await self._kvs.set_value(item.key, None)
                        else:
                            logger.debug(f'Valid cache item {item.key}')
                    if i == self._expiration_max_items:
                        break
                    i += 1

            self._async_thread.run_coro(expire_kvs())

        logger.debug('Closing cache storage')
        try:
            self._async_thread.close()
        except KeyboardInterrupt:
            logger.warning('Shutdown interrupted by KeyboardInterrupt!')
        except Exception:
            logger.exception('Exception occurred while shutting down cache storage')
        finally:
            logger.debug('Cache storage closed')

    def retrieve_response(self, _: Spider, request: Request, current_time: int | None = None) -> Response | None:
        """Retrieve a response from the cache storage."""
        if self._async_thread is None:
            raise ValueError('Async thread not initialized')
        if self._kvs is None:
            raise ValueError('Key value store not initialized')
        if self._fingerprinter is None:
            raise ValueError('Request fingerprinter not initialized')

        key = self._fingerprinter.fingerprint(request).hex()
        value = self._async_thread.run_coro(self._kvs.get_value(key))

        if value is None:
            logger.debug('Cache miss', extra={'request': request})
            return None

        if current_time is None:
            current_time = int(time())
        if 0 < self._expiration_secs < current_time - read_gzip_time(value):
            logger.debug('Cache expired', extra={'request': request})
            return None

        data = from_gzip(value)
        url = data['url']
        status = data['status']
        headers = Headers(data['headers'])
        body = data['body']
        respcls = responsetypes.from_args(headers=headers, url=url, body=body)

        logger.debug('Cache hit', extra={'request': request})
        return respcls(url=url, headers=headers, status=status, body=body)

    def store_response(self, _: Spider, request: Request, response: Response) -> None:
        """Store a response in the cache storage."""
        if self._async_thread is None:
            raise ValueError('Async thread not initialized')
        if self._kvs is None:
            raise ValueError('Key value store not initialized')
        if self._fingerprinter is None:
            raise ValueError('Request fingerprinter not initialized')

        key = self._fingerprinter.fingerprint(request).hex()
        data = {
            'status': response.status,
            'url': response.url,
            'headers': dict(response.headers),
            'body': response.body,
        }
        value = to_gzip(data)
        self._async_thread.run_coro(self._kvs.set_value(key, value))


def to_gzip(data: dict, mtime: int | None = None) -> bytes:
    """Dump a dictionary to a gzip-compressed byte stream."""
    with io.BytesIO() as byte_stream:
        with gzip.GzipFile(fileobj=byte_stream, mode='wb', mtime=mtime) as gzip_file:
            pickle.dump(data, gzip_file, protocol=4)
        return byte_stream.getvalue()


def from_gzip(gzip_bytes: bytes) -> dict:
    """Load a dictionary from a gzip-compressed byte stream."""
    with io.BytesIO(gzip_bytes) as byte_stream, gzip.GzipFile(fileobj=byte_stream, mode='rb') as gzip_file:
        data: dict = pickle.load(gzip_file)
        return data


def read_gzip_time(gzip_bytes: bytes) -> int:
    """Read the modification time from a gzip-compressed byte stream without decompressing the data."""
    header = gzip_bytes[:10]
    header_components = struct.unpack('<HBBI2B', header)
    mtime: int = header_components[3]
    return mtime


def get_kvs_name(spider_name: str, max_length: int = 60) -> str:
    """Get the key value store name for a spider.

    The key value store name is derived from the spider name by replacing all special characters
    with hyphens and trimming leading and trailing hyphens. The resulting name is prefixed with
    'httpcache-' and truncated to the maximum length.

    The documentation
    [about storages](https://docs.apify.com/platform/storage/usage#named-and-unnamed-storages)
    mentions that names can be up to 63 characters long, so the default max length is set to 60.

    Such naming isn't unique per spider, but should be sufficiently unique for most use cases.
    The name of the key value store should indicate to which spider it belongs, e.g. in
    the listing in the Apify's console.

    Args:
        spider_name: Value of the Spider instance's name attribute.
        max_length: Maximum length of the key value store name.

    Returns: Key value store name.

    Raises:
        ValueError: If the spider name contains only special characters.
    """
    slug = re.sub(r'[^a-zA-Z0-9-]', '-', spider_name)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    if not slug:
        raise ValueError(f'Unsupported spider name: {spider_name!r} (slug: {slug!r})')
    return f'httpcache-{slug}'[:max_length]
