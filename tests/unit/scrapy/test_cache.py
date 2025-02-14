from time import time

from apify.scrapy.cache import from_gzip, read_gzip_time, to_gzip

FIXTURE_BYTES = (
    b'\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xffk`\x99*\xcc\x00\x01\xb5SzX\xf2\x12s'
    b'S\xa7\xf4\xb0:\xe6d&\xa7N)\xd6\x03\x00\x1c\xe8U\x9c\x1e\x00\x00\x00'
)


def test_gzip() -> None:
    assert from_gzip(to_gzip({'name': 'Alice'})) == {'name': 'Alice'}


def test_to_gzip() -> None:
    data_bytes = to_gzip({'name': 'Alice'}, mtime=0)

    assert data_bytes == FIXTURE_BYTES


def test_from_gzip() -> None:
    data_dict = from_gzip(FIXTURE_BYTES)

    assert data_dict == {'name': 'Alice'}


def test_read_gzip_time() -> None:
    assert read_gzip_time(FIXTURE_BYTES) == 0


def test_read_gzip_time_non_zero() -> None:
    current_time = int(time())
    data_bytes = to_gzip({'name': 'Alice'}, mtime=current_time)

    assert read_gzip_time(data_bytes) == current_time
