from __future__ import annotations

import pytest
from scrapy import Request, Spider
from scrapy.http.headers import Headers

from apify.scrapy.requests import to_apify_request


class DummySpider(Spider):
    name = 'dummy_spider'


@pytest.fixture
def spider() -> DummySpider:
    """Fixture to create a "dummy" Scrapy spider."""
    return DummySpider()


def test__to_apify_request__simple(spider: Spider) -> None:
    scrapy_request = Request(url='https://example.com')

    apify_request = to_apify_request(scrapy_request, spider)
    assert apify_request is not None
    assert apify_request.url == 'https://example.com'

    user_data = apify_request.user_data
    assert isinstance(user_data, dict)
    assert 'scrapy_request' in user_data
    assert isinstance(user_data.get('scrapy_request'), str)


def test__to_apify_request__headers(spider: Spider) -> None:
    scrapy_request_headers = Headers({'Authorization': 'Bearer access_token'})
    scrapy_request = Request(url='https://example.com', headers=scrapy_request_headers)

    apify_request = to_apify_request(scrapy_request, spider)

    assert apify_request is not None
    assert apify_request.headers == dict(scrapy_request_headers.to_unicode_dict())


def test__to_apify_request__without_id_and_unique_key(spider: Spider) -> None:
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

    assert isinstance(user_data, dict)
    assert user_data['some_user_data'] == 'test'
    assert 'scrapy_request' in user_data
    assert isinstance(user_data.get('scrapy_request'), str)


def test__to_apify_request__with_id_and_unique_key(spider: Spider) -> None:
    scrapy_request = Request(
        url='https://example.com',
        method='GET',
        meta={
            'apify_request_id': 'abc123',
            'apify_request_unique_key': 'https://example.com',
            'userData': {'some_user_data': 'hello'},
        },
    )

    apify_request = to_apify_request(scrapy_request, spider)
    assert apify_request is not None

    assert apify_request.url == 'https://example.com'
    assert apify_request.method == 'GET'
    assert apify_request.id == 'abc123'
    assert apify_request.unique_key == 'https://example.com'

    user_data = apify_request.user_data

    assert isinstance(user_data, dict)
    assert user_data['some_user_data'] == 'hello'
    assert 'scrapy_request' in user_data
    assert isinstance(user_data.get('scrapy_request'), str)


def test__to_apify_request__invalid_scrapy_request(spider: Spider) -> None:
    scrapy_request = 'invalid_request'

    apify_request = to_apify_request(scrapy_request, spider)
    assert apify_request is None
