from __future__ import annotations

import gzip
import io
import pickle
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

    This cache storage requires the asyncio Twisted reactor to be installed.
    """

    def __init__(self, settings: BaseSettings) -> None:
        self._expiration_max_items = 100
        self._expiration_secs: int = settings.getint('HTTPCACHE_EXPIRATION_SECS')
        self._spider: Spider | None = None
        self._kv: KeyValueStore | None = None
        self._fingerprinter: RequestFingerprinterProtocol | None = None
        self._async_thread: AsyncThread | None = None

    def open_spider(self, spider: Spider) -> None:
        """Open the cache storage for a spider."""
        logger.debug('Using Apify key value cache storage', extra={'spider': spider})
        self._spider = spider
        self._fingerprinter = spider.crawler.request_fingerprinter
        kv_name = f'httpcache-{spider.name}'

        async def open_kv() -> KeyValueStore:
            config = Configuration.get_global_configuration()
            if config.is_at_home:
                storage_client = ApifyStorageClient.from_config(config)
                return await KeyValueStore.open(name=kv_name, storage_client=storage_client)
            return await KeyValueStore.open(name=kv_name)

        logger.debug("Starting background thread for cache storage's event loop")
        self._async_thread = AsyncThread()
        logger.debug(f"Opening cache storage's {kv_name!r} key value store")
        self._kv = self._async_thread.run_coro(open_kv())

    def close_spider(self, _: Spider, current_time: int | None = None) -> None:
        """Close the cache storage for a spider."""
        if self._async_thread is None:
            raise ValueError('Async thread not initialized')

        logger.info(f'Cleaning up cache items (max {self._expiration_max_items})')
        if self._expiration_secs > 0:
            if current_time is None:
                current_time = int(time())

            async def expire_kv() -> None:
                if self._kv is None:
                    raise ValueError('Key value store not initialized')
                i = 0
                async for item in self._kv.iterate_keys():
                    value = await self._kv.get_value(item.key)
                    try:
                        gzip_time = read_gzip_time(value)
                    except Exception as e:
                        logger.warning(f'Malformed cache item {item.key}: {e}')
                        await self._kv.set_value(item.key, None)
                    else:
                        if self._expiration_secs < current_time - gzip_time:
                            logger.debug(f'Expired cache item {item.key}')
                            await self._kv.set_value(item.key, None)
                        else:
                            logger.debug(f'Valid cache item {item.key}')
                    if i == self._expiration_max_items:
                        break
                    i += 1

            self._async_thread.run_coro(expire_kv())

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
        if self._kv is None:
            raise ValueError('Key value store not initialized')
        if self._fingerprinter is None:
            raise ValueError('Request fingerprinter not initialized')

        key = self._fingerprinter.fingerprint(request).hex()
        value = self._async_thread.run_coro(self._kv.get_value(key))

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
        if self._kv is None:
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
        self._async_thread.run_coro(self._kv.set_value(key, value))


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
