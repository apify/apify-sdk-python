import asyncio
import gzip
import io
import json
import pickle
from time import time
from typing import Any

import pytest
from scrapy import Request
from scrapy.settings import Settings

from apify.scrapy.extensions._httpcache import ApifyCacheStorage, from_gzip, get_kvs_name, read_gzip_time, to_gzip

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
