from __future__ import annotations

import asyncio
import gzip
import io
import json
import pickle
from time import time
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from scrapy import Request
from scrapy.settings import Settings

from apify.scrapy.extensions._httpcache import ApifyCacheStorage, from_gzip, get_kvs_name, read_gzip_time, to_gzip

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

FIXTURE_DICT = {'name': 'Alice'}

# Gzip-compressed JSON (the pickle-free format) of FIXTURE_DICT with mtime=0.
FIXTURE_BYTES = (
    b'\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff\xabV\xcaK\xccMU\xb2RPr\xcc\xc9LNU'
    b'\xaa\x05\x00\x03\x9a\x9d\xb0\x11\x00\x00\x00'
)


def test_gzip() -> None:
    assert from_gzip(to_gzip(FIXTURE_DICT)) == FIXTURE_DICT


def test_to_gzip() -> None:
    data_bytes = to_gzip(FIXTURE_DICT, mtime=0)

    assert data_bytes == FIXTURE_BYTES


def test_from_gzip() -> None:
    data_dict = from_gzip(FIXTURE_BYTES)

    assert data_dict == FIXTURE_DICT


def test_read_gzip_time() -> None:
    assert read_gzip_time(FIXTURE_BYTES) == 0


def test_read_gzip_time_non_zero() -> None:
    current_time = int(time())
    data_bytes = to_gzip(FIXTURE_DICT, mtime=current_time)

    assert read_gzip_time(data_bytes) == current_time


def test_gzip_round_trips_binary_response() -> None:
    """A cached response with a binary body and Scrapy-style bytes headers round-trips."""
    data = {
        'status': 200,
        'url': 'https://example.com',
        'headers': {b'Content-Type': [b'text/html'], b'X-Bin': [b'\x00\xff']},
        'body': b'<html>\xff\xfe</html>',
    }

    assert from_gzip(to_gzip(data)) == data


def test_from_gzip_rejects_pickle_payload() -> None:
    """Cache entries are stored as gzip-compressed JSON; a pickle payload is not valid JSON.

    The loader must reject such a payload rather than load it.
    """
    with io.BytesIO() as byte_stream:
        with gzip.GzipFile(fileobj=byte_stream, mode='wb') as gzip_file:
            pickle.dump({'status': 200, 'body': b'x'}, gzip_file, protocol=4)
        pickle_payload = byte_stream.getvalue()

    with pytest.raises((UnicodeDecodeError, json.JSONDecodeError, ValueError)):
        from_gzip(pickle_payload)


class _FakeAsyncThread:
    def run_coro(self, coro: Any, *_: Any, **__: Any) -> Any:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def close(self) -> None:
        """No-op; `close_spider` calls this when shutting the cache storage down."""


class _FakeKvs:
    def __init__(self, value: bytes | None) -> None:
        self._value = value

    async def get_value(self, _: str) -> bytes | None:
        return self._value


class _FakeFingerprinter:
    def fingerprint(self, _: Request) -> bytes:
        return b'\xab\xcd'


def _make_storage(value: bytes | None) -> ApifyCacheStorage:
    storage = ApifyCacheStorage(Settings({'HTTPCACHE_EXPIRATION_SECS': 0}))
    storage._async_thread = _FakeAsyncThread()  # ty: ignore[invalid-assignment]
    storage._kvs = _FakeKvs(value)  # ty: ignore[invalid-assignment]
    storage._fingerprinter = _FakeFingerprinter()  # ty: ignore[invalid-assignment]
    return storage


def test_retrieve_response_returns_cached_response() -> None:
    data = {'status': 200, 'url': 'https://example.com', 'headers': {}, 'body': b'hello'}
    storage = _make_storage(to_gzip(data))
    response = storage.retrieve_response(None, Request('https://example.com'))  # ty: ignore[invalid-argument-type]
    assert response is not None
    assert response.status == 200
    assert response.body == b'hello'


def test_retrieve_response_ignores_legacy_pickle_item() -> None:
    # A gzip-wrapped pickle payload is the legacy (pre-JSON) cache format that the JSON reader cannot
    # load. After the upgrade, such an item must degrade to a cache miss instead of raising and breaking
    # the download, so the cache self-heals (re-fetch and re-store as JSON) rather than crashing.
    with io.BytesIO() as byte_stream:
        with gzip.GzipFile(fileobj=byte_stream, mode='wb') as gzip_file:
            pickle.dump({'status': 200, 'body': b'x'}, gzip_file, protocol=4)
        legacy_pickle = byte_stream.getvalue()
    storage = _make_storage(legacy_pickle)
    assert storage.retrieve_response(None, Request('https://example.com')) is None  # ty: ignore[invalid-argument-type]


def test_retrieve_response_missing_key_is_cache_miss() -> None:
    """A cache value that decodes to a dict missing an expected key degrades to a miss, not a KeyError.

    The field reads sit inside the crash-guard, so a forward/older or truncated-but-valid JSON payload
    (here one without a `url`) is ignored rather than raising out of `retrieve_response`.
    """
    value = to_gzip({'status': 200, 'headers': {}, 'body': b'x'})  # no 'url'
    storage = _make_storage(value)
    assert storage.retrieve_response(None, Request('https://example.com')) is None  # ty: ignore[invalid-argument-type]


class _KeyIterator:
    """A plain async iterator over a snapshot of keys (not a generator, so an early `break` needs no close)."""

    def __init__(self, keys: list[str]) -> None:
        self._keys = keys
        self._index = 0

    def __aiter__(self) -> _KeyIterator:
        return self

    async def __anext__(self) -> Any:
        if self._index >= len(self._keys):
            raise StopAsyncIteration
        key = self._keys[self._index]
        self._index += 1
        return SimpleNamespace(key=key)


class _RecordingKvs:
    """An in-memory key-value store double for the cleanup sweep that records deletions."""

    def __init__(self, items: dict[str, bytes | None]) -> None:
        self._items = dict(items)
        self.deleted: list[str] = []

    def iterate_keys(self) -> AsyncIterator[Any]:
        # Snapshot the keys, mirroring the real clients (so deleting while iterating is safe).
        return _KeyIterator(list(self._items))

    async def get_value(self, key: str) -> bytes | None:
        return self._items.get(key)

    async def delete_value(self, key: str) -> None:
        self.deleted.append(key)
        self._items.pop(key, None)


def _make_cleanup_storage(
    items: dict[str, bytes | None],
    *,
    expiration_secs: int,
    max_items: int = 100,
) -> tuple[ApifyCacheStorage, _RecordingKvs]:
    storage = ApifyCacheStorage(
        Settings({'HTTPCACHE_EXPIRATION_SECS': expiration_secs, 'APIFY_HTTPCACHE_EXPIRATION_MAX_ITEMS': max_items})
    )
    storage._async_thread = _FakeAsyncThread()  # ty: ignore[invalid-assignment]
    kvs = _RecordingKvs(items)
    storage._kvs = kvs  # ty: ignore[invalid-assignment]
    return storage, kvs


def test_close_spider_deletes_expired_and_malformed_but_keeps_valid() -> None:
    """The close-spider cleanup deletes expired and unreadable entries and leaves fresh ones in place."""
    current_time = 1000
    fresh = {'status': 200, 'url': 'https://example.com', 'headers': {}, 'body': b''}
    items: dict[str, bytes | None] = {
        'expired': to_gzip(fresh, mtime=0),  # age 1000s > expiration 100s
        'valid': to_gzip(fresh, mtime=current_time),  # age 0s
        'malformed': b'bad',  # too short for read_gzip_time to parse the mtime header
    }
    storage, kvs = _make_cleanup_storage(items, expiration_secs=100)

    storage.close_spider(None, current_time=current_time)  # ty: ignore[invalid-argument-type]

    assert set(kvs.deleted) == {'expired', 'malformed'}


def test_close_spider_respects_max_items() -> None:
    """At most `APIFY_HTTPCACHE_EXPIRATION_MAX_ITEMS` entries are swept per close (exactly max, not max+1)."""
    current_time = 1000
    expired = to_gzip({'status': 200, 'url': 'https://example.com', 'headers': {}, 'body': b''}, mtime=0)
    items: dict[str, bytes | None] = {f'k{i}': expired for i in range(5)}
    storage, kvs = _make_cleanup_storage(items, expiration_secs=100, max_items=2)

    storage.close_spider(None, current_time=current_time)  # ty: ignore[invalid-argument-type]

    assert len(kvs.deleted) == 2


@pytest.mark.parametrize(
    ('spider_name', 'expected'),
    [
        ('test', 'httpcache-test'),
        ('123', 'httpcache-123'),
        ('test-spider', 'httpcache-test-spider'),
        ('test_spider', 'httpcache-test-spider'),
        ('test spider', 'httpcache-test-spider'),
        ('test👻spider', 'httpcache-test-spider'),
        ('test@spider', 'httpcache-test-spider'),
        ('   test   spider   ', 'httpcache-test-spider'),
        ('testspider.com', 'httpcache-testspider-com'),
        ('t' * 100, 'httpcache-tttttttttttttttttttttttttttttttttttttttttttttttttt'),
    ],
)
def test_get_kvs_name(spider_name: str, expected: str) -> None:
    assert get_kvs_name(spider_name) == expected


@pytest.mark.parametrize(
    ('spider_name'),
    [
        '',
        '-',
        '-@-/-',
    ],
)
def test_get_kvs_name_raises(spider_name: str) -> None:
    with pytest.raises(ValueError, match=r'Unsupported spider name'):
        assert get_kvs_name(spider_name)
