import asyncio
import gzip
from time import time
from typing import Any

import pytest
from scrapy import Request
from scrapy.settings import Settings

from apify.scrapy.extensions._httpcache import ApifyCacheStorage, from_gzip, get_kvs_name, read_gzip_time, to_gzip

FIXTURE_DICT = {'name': 'Alice'}

FIXTURE_BYTES = (
    b'\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xffk`\x99*\xcc\x00\x01\xb5SzX\xf2\x12s'
    b'S\xa7\xf4\xb0:\xe6d&\xa7N)\xd6\x03\x00\x1c\xe8U\x9c\x1e\x00\x00\x00'
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


# Helpers for driving `ApifyCacheStorage.retrieve_response` without a real KVS or event loop thread.


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


def test_retrieve_response_ignores_malformed_item() -> None:
    # A gzip-wrapped JSON payload is a legacy/foreign cache format that the pickle reader cannot
    # load. Such an item must degrade to a cache miss instead of raising and breaking the download.
    storage = _make_storage(gzip.compress(b'{"status": 200}'))

    assert storage.retrieve_response(None, Request('https://example.com')) is None  # ty: ignore[invalid-argument-type]
