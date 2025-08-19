from __future__ import annotations

import pytest
from scrapy import Request, Spider
from scrapy.http.headers import Headers

from crawlee._types import HttpHeaders

from apify.scrapy.requests import to_apify_request


class DummySpider(Spider):
    name = 'dummy_spider'


@pytest.fixture
def spider() -> DummySpider:
    """Fixture to create a "dummy" Scrapy spider."""
    return DummySpider()


def test_creates_simple_request(spider: Spider) -> None:
    scrapy_request = Request(url='https://example.com')

    apify_request = to_apify_request(scrapy_request, spider)
    assert apify_request is not None
    assert apify_request.url == 'https://example.com'

    user_data = apify_request.user_data
    assert 'scrapy_request' in user_data
    assert isinstance(user_data.get('scrapy_request'), str)


def test_handles_headers(spider: Spider) -> None:
    scrapy_request_headers = Headers({'Authorization': 'Bearer access_token'})
    scrapy_request = Request(url='https://example.com', headers=scrapy_request_headers)

    apify_request = to_apify_request(scrapy_request, spider)

    assert apify_request is not None
    assert apify_request.headers == HttpHeaders(dict(scrapy_request_headers.to_unicode_dict()))


def test_without_id_and_unique_key(spider: Spider) -> None:
    scrapy_request = Request(
        url='https://example.com',
        method='GET',
        meta={'userData': {'some_user_data': 'test'}},
    )

    apify_request = to_apify_request(scrapy_request, spider)

    assert apify_request is not None
    assert apify_request.url == 'https://example.com'
    assert apify_request.method == 'GET'

    user_data = apify_request.user_data

    assert user_data['some_user_data'] == 'test'
    assert 'scrapy_request' in user_data
    assert isinstance(user_data.get('scrapy_request'), str)


def test_with_id_and_unique_key(spider: Spider) -> None:
    scrapy_request = Request(
        url='https://example.com',
        method='GET',
        meta={
            'apify_request_unique_key': 'https://example.com',
            'userData': {'some_user_data': 'hello'},
        },
    )

    apify_request = to_apify_request(scrapy_request, spider)
    assert apify_request is not None

    assert apify_request.url == 'https://example.com'
    assert apify_request.method == 'GET'
    assert apify_request.unique_key == 'https://example.com'

    user_data = apify_request.user_data

    assert user_data['some_user_data'] == 'hello'
    assert 'scrapy_request' in user_data
    assert isinstance(user_data.get('scrapy_request'), str)


def test_invalid_scrapy_request_returns_none(spider: Spider) -> None:
    scrapy_request = 'invalid_request'

    apify_request = to_apify_request(scrapy_request, spider)  # type: ignore[arg-type]
    assert apify_request is None
