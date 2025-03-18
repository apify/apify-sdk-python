from time import time

import pytest

from apify.scrapy.extensions._httpcache import from_gzip, get_kvs_name, read_gzip_time, to_gzip

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
    with pytest.raises(ValueError, match='Unsupported spider name'):
        assert get_kvs_name(spider_name)
