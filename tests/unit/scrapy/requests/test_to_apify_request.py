from __future__ import annotations

import pytest
from scrapy import Request, Spider
from scrapy.http.headers import Headers

from crawlee._types import HttpHeaders

from apify.scrapy.requests import to_apify_request, to_scrapy_request


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

    apify_request = to_apify_request(scrapy_request, spider)  # ty: ignore[invalid-argument-type]
    assert apify_request is None


def test_roundtrip_follow_up_request_with_propagated_userdata(spider: Spider) -> None:
    """Reproduce: CrawleeRequestData() argument after ** must be a mapping, not CrawleeRequestData.

    After two roundtrips through to_apify_request/to_scrapy_request with userData propagation,
    Request.from_url() writes a CrawleeRequestData object into UserData.__pydantic_extra__['__crawlee'].
    On the next roundtrip, this CrawleeRequestData object is found by user_data_dict.get('__crawlee')
    and passed to CrawleeRequestData(**obj), which fails because CrawleeRequestData is not a mapping.
    """
    # Step 1: Initial request -> first roundtrip
    initial_scrapy_request = Request(url='https://example.com/page')
    apify_request_1 = to_apify_request(initial_scrapy_request, spider)
    assert apify_request_1 is not None
    scrapy_request_1 = to_scrapy_request(apify_request_1, spider)

    # Step 2: Spider yields follow-up with propagated userData -> second roundtrip
    follow_up_1 = Request(
        url='https://example.com/page2',
        meta={'userData': scrapy_request_1.meta['userData']},
    )
    apify_request_2 = to_apify_request(follow_up_1, spider)
    assert apify_request_2 is not None
    scrapy_request_2 = to_scrapy_request(apify_request_2, spider)

    # Step 3: Spider yields another follow-up with propagated userData from 2nd roundtrip.
    # This fails because userData now has __crawlee as CrawleeRequestData in __pydantic_extra__.
    follow_up_2 = Request(
        url='https://example.com/image.png',
        meta={'userData': scrapy_request_2.meta['userData']},
    )
    follow_up_apify_request = to_apify_request(follow_up_2, spider)
    assert follow_up_apify_request is not None
    assert follow_up_apify_request.url == 'https://example.com/image.png'
