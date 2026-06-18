from __future__ import annotations

import gzip
import io
import re
import struct
from datetime import timedelta
from logging import getLogger
from time import time
from typing import TYPE_CHECKING

from scrapy.http.headers import Headers
from scrapy.responsetypes import responsetypes

from apify import Configuration
from apify.scrapy._async_thread import AsyncThread
from apify.scrapy._serialization import decode_from_json, encode_to_json
from apify.storage_clients import ApifyStorageClient
from apify.storages import KeyValueStore

if TYPE_CHECKING:
    from scrapy import Request, Spider
    from scrapy.http.response import Response
    from scrapy.settings import BaseSettings
    from scrapy.utils.request import RequestFingerprinterProtocol

logger = getLogger(__name__)


class ApifyCacheStorage:
    """A Scrapy cache storage that uses the Apify `KeyValueStore` to store responses.

    It can be set as a storage for Scrapy's built-in `HttpCacheMiddleware`, which caches responses to requests.
    See HTTPCache middleware settings (prefixed with `HTTPCACHE_`) in the Scrapy documentation for more information.
    Requires the asyncio Twisted reactor to be installed.
    """

    def __init__(self, settings: BaseSettings) -> None:
        self._expiration_max_items: int = settings.getint('APIFY_HTTPCACHE_EXPIRATION_MAX_ITEMS', 100)
        """Upper bound on how many keys the per-spider-close cleanup sweeps (best-effort; `close_spider`)."""

        self._async_thread_timeout = timedelta(seconds=settings.getint('APIFY_ASYNC_THREAD_TIMEOUT_SECS', 60))
        """Caps how long each coroutine run on the background event loop may take."""

        self._expiration_secs: int = settings.getint('HTTPCACHE_EXPIRATION_SECS')
        """Seconds a cached entry stays fresh; older entries are treated as expired, and `0` disables expiration."""

        self._spider: Spider | None = None
        """The Scrapy `Spider` this cache storage is bound to; set in `open_spider`."""

        self._kvs: KeyValueStore | None = None
        """The Apify `KeyValueStore` backing the cache; opened in `open_spider`."""

        self._fingerprinter: RequestFingerprinterProtocol | None = None
        """Scrapy's request fingerprinter, used to derive the cache key for each request."""

        self._async_thread: AsyncThread | None = None
        """Background event-loop thread that runs the storage coroutines from Scrapy's synchronous callbacks."""

    def open_spider(self, spider: Spider) -> None:
        """Open the cache storage for a spider.

        Starts the background event-loop thread and opens the spider's key-value store. If opening the store
        fails, the freshly started thread is closed so it is not leaked.

        Args:
            spider: The spider the cache storage is being opened for.
        """
        logger.debug('Using Apify key value cache storage', extra={'spider': spider})
        self._spider = spider
        self._fingerprinter = spider.crawler.request_fingerprinter
        kvs_name = get_kvs_name(spider.name)

        async def open_kvs() -> KeyValueStore:
            configuration = Configuration.get_global_configuration()
            if configuration.is_at_home:
                storage_client = ApifyStorageClient()
                return await KeyValueStore.open(
                    name=kvs_name,
                    configuration=configuration,
                    storage_client=storage_client,
                )
            return await KeyValueStore.open(name=kvs_name)

        logger.debug("Starting background thread for cache storage's event loop")
        self._async_thread = AsyncThread(default_timeout=self._async_thread_timeout)
        logger.debug(f"Opening cache storage's {kvs_name!r} key value store")

        try:
            self._kvs = self._async_thread.run_coro(open_kvs())
        except Exception:
            logger.exception('Failed to open the cache key-value store.')
            # Opening the key-value store failed, so close the freshly started async thread instead of
            # leaking its event-loop thread (`close_spider` may never run if `open_spider` fails). Guard
            # the close so a secondary failure here cannot mask the original error.
            try:
                self._async_thread.close()
            except Exception:
                logger.exception('Failed to close the async thread after a failed cache storage open.')
            raise

    def close_spider(self, _: Spider, current_time: int | None = None) -> None:
        """Close the cache storage for a spider.

        Runs a best-effort cleanup sweep that deletes expired entries when expiration is enabled, then shuts
        down the background event-loop thread. The thread is always closed, even if the sweep fails.

        Args:
            _: The spider being closed. Part of Scrapy's storage interface, unused here.
            current_time: Unix time in seconds used as the current time when deciding which entries have
                expired. Defaults to the current time.
        """
        if self._async_thread is None:
            raise ValueError('Async thread not initialized')

        if current_time is None:
            current_time = int(time())

        logger.info(f'Cleaning up cache items (max {self._expiration_max_items})')

        # Best-effort: a cleanup failure is logged and swallowed (the sweep only reclaims storage, so failing it
        # must not turn a normal spider close into an error), and `close` always runs in the `finally`, so
        # neither the failure nor an early return can leak the event-loop thread.
        try:
            if self._expiration_secs > 0:
                self._async_thread.run_coro(self._expire_kvs(current_time))
        except Exception:
            logger.exception('Failed to clean up expired cache items.')
        finally:
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
        """Retrieve a cached response for a request.

        A malformed, legacy, or expired cache entry is treated as a miss, so Scrapy re-fetches the request and
        re-stores it in the current format.

        Args:
            _: The spider making the request. Part of Scrapy's storage interface, unused here.
            request: The request to look up in the cache.
            current_time: Unix time in seconds used as the current time when checking whether the entry has
                expired. Defaults to the current time.

        Returns:
            The cached response on a hit, or `None` on a miss, an expired entry, or an unreadable entry.
        """
        if self._async_thread is None:
            raise ValueError('Async thread not initialized')
        if self._kvs is None:
            raise ValueError('Key value store not initialized')
        if self._fingerprinter is None:
            raise ValueError('Request fingerprinter not initialized')

        key = self._fingerprinter.fingerprint(request).hex()
        # Log here before re-raising: this coroutine ran on a separate event-loop thread, and the failure is
        # otherwise easy to lose as it crosses that thread boundary back into Scrapy's synchronous machinery.
        try:
            value = self._async_thread.run_coro(self._kvs.get_value(key))
        except Exception:
            logger.exception('Failed to retrieve a response from the cache.')
            raise

        if value is None:
            logger.debug('Cache miss', extra={'request': request})
            return None

        if current_time is None:
            current_time = int(time())

        # A malformed or legacy cache entry must not crash retrieval; treat it as a cache miss so Scrapy re-fetches
        # and re-stores it in the current format. The field reads stay inside the `try` as well: a value that decodes
        # to a dict missing any expected key (a forward/older format, or a truncated-but-valid JSON payload) must
        # also degrade to a miss rather than raising an uncaught `KeyError`.
        try:
            if 0 < self._expiration_secs < current_time - read_gzip_time(value):
                logger.debug('Cache expired', extra={'request': request})
                return None

            data = from_gzip(value)
            url = data['url']
            status = data['status']
            headers = Headers(data['headers'])
            body = data['body']
        except Exception as exc:
            logger.warning(f'Ignoring malformed cache entry {key!r}: {exc}', extra={'request': request})
            return None

        respcls = responsetypes.from_args(headers=headers, url=url, body=body)
        logger.debug('Cache hit', extra={'request': request})
        return respcls(url=url, headers=headers, status=status, body=body)

    def store_response(self, _: Spider, request: Request, response: Response) -> None:
        """Store a response in the cache storage.

        Args:
            _: The spider that produced the response. Part of Scrapy's storage interface, unused here.
            request: The request the response belongs to. Its fingerprint is used as the cache key.
            response: The response to store in the cache.
        """
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
        # Log here before re-raising: this coroutine ran on a separate event-loop thread, and the failure is
        # otherwise easy to lose as it crosses that thread boundary back into Scrapy's synchronous machinery.
        try:
            self._async_thread.run_coro(self._kvs.set_value(key, value))
        except Exception:
            logger.exception('Failed to store a response in the cache.')
            raise

    async def _expire_kvs(self, current_time: int) -> None:
        """Sweep the cache key-value store, deleting expired or unreadable entries.

        Best-effort cleanup: at most `_expiration_max_items` keys per close, in no guaranteed order, so stale
        entries may linger. This only reclaims storage; `retrieve_response` already treats an expired entry as
        a cache miss.
        """
        if self._kvs is None:
            raise ValueError('Key value store not initialized')

        processed = 0

        async for item in self._kvs.iterate_keys():
            if processed >= self._expiration_max_items:
                break

            processed += 1
            value = await self._kvs.get_value(item.key)

            try:
                gzip_time = read_gzip_time(value)
            except Exception as exc:
                logger.warning(f'Malformed cache item {item.key}: {exc}')
                await self._kvs.delete_value(item.key)
            else:
                if self._expiration_secs < current_time - gzip_time:
                    logger.debug(f'Expired cache item {item.key}')
                    await self._kvs.delete_value(item.key)


def to_gzip(data: dict, mtime: int | None = None) -> bytes:
    """Dump a dictionary to a gzip-compressed JSON byte stream.

    Cache entries live in the Apify key-value store, which holds JSON, so they are serialized as JSON rather
    than pickled. See `apify.scrapy._serialization` for the encoding.
    """
    payload = encode_to_json(data).encode('utf-8')
    with io.BytesIO() as byte_stream:
        with gzip.GzipFile(fileobj=byte_stream, mode='wb', mtime=mtime) as gzip_file:
            gzip_file.write(payload)
        return byte_stream.getvalue()


def from_gzip(gzip_bytes: bytes) -> dict:
    """Load a dictionary from a gzip-compressed JSON byte stream."""
    with io.BytesIO(gzip_bytes) as byte_stream, gzip.GzipFile(fileobj=byte_stream, mode='rb') as gzip_file:
        data = decode_from_json(gzip_file.read().decode('utf-8'))
    if not isinstance(data, dict):
        raise TypeError(f'Expected a dict from the cached payload, got {type(data)}')
    return data


def read_gzip_time(gzip_bytes: bytes) -> int:
    """Read the modification time from a gzip-compressed byte stream without decompressing the data."""
    header = gzip_bytes[:10]
    header_components = struct.unpack('<HBBI2B', header)
    mtime: int = header_components[3]
    return mtime


def get_kvs_name(spider_name: str, max_length: int = 60) -> str:
    """Get the key value store name for a spider.

    The key value store name is derived from the spider name by replacing all special characters with hyphens
    and trimming leading and trailing hyphens. The resulting name is prefixed with 'httpcache-' and truncated
    to the maximum length.

    The documentation [about storages](https://docs.apify.com/platform/storage/usage#named-and-unnamed-storages)
    mentions that names can be up to 63 characters long, so the default max length is set to 60.

    Such naming isn't unique per spider, but should be sufficiently unique for most use cases. The name
    of the key-value store should indicate to which spider it belongs, e.g. in the listing in the Apify's console.

    Args:
        spider_name: Value of the Spider instance's name attribute.
        max_length: Maximum length of the key value store name.

    Returns:
        Key value store name.

    Raises:
        ValueError: If the spider name contains only special characters.
    """
    slug = re.sub(r'[^a-zA-Z0-9-]', '-', spider_name)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    if not slug:
        raise ValueError(f'Unsupported spider name: {spider_name!r} (slug: {slug!r})')
    return f'httpcache-{slug}'[:max_length]
