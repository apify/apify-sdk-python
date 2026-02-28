from time import time

import pytest

from apify.scrapy.extensions._httpcache import from_gzip, get_kvs_name, read_gzip_time, to_gzip

FIXTURE_DICT = {'name': 'Alice'}

FIXTURE_BYTES = (
    b'\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff\xabV\xcaK\xccMU\xb2RPr\xcc\xc9LNU\xaa\x05\x00'
    b'\x03\x9a\x9d\xb0\x11\x00\x00\x00'
)


def test_gzip() -> None:
    assert from_gzip(to_gzip(FIXTURE_DICT)) == FIXTURE_DICT


def test_gzip_with_bytes_values() -> None:
    data = {
        'status': 200,
        'url': 'https://example.com',
        'headers': {b'Content-Type': [b'text/html']},
        'body': b'<html>Hello</html>',
    }
    result = from_gzip(to_gzip(data))
    # After JSON roundtrip, bytes keys become strings, bytes values are preserved
    assert result['status'] == 200
    assert result['url'] == 'https://example.com'
    assert result['headers']['Content-Type'] == [b'text/html']
    assert result['body'] == b'<html>Hello</html>'


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
