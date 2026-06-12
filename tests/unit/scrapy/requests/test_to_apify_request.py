from __future__ import annotations

import json
import logging
from typing import cast

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
    """A simple Scrapy request converts to an Apify request carrying the serialized `scrapy_request`."""
    scrapy_request = Request(url='https://example.com')

    apify_request = to_apify_request(scrapy_request, spider)
    assert apify_request is not None
    assert apify_request.url == 'https://example.com'

    user_data = apify_request.user_data
    assert 'scrapy_request' in user_data
    assert isinstance(user_data.get('scrapy_request'), str)


def test_handles_headers(spider: Spider) -> None:
    """Scrapy request headers are carried onto the Apify request as `HttpHeaders`."""
    scrapy_request_headers = Headers({'Authorization': 'Bearer access_token'})
    scrapy_request = Request(url='https://example.com', headers=scrapy_request_headers)

    apify_request = to_apify_request(scrapy_request, spider)

    assert apify_request is not None
    expected_headers = cast('dict[str, str]', dict(scrapy_request_headers.to_unicode_dict()))
    assert apify_request.headers == HttpHeaders(expected_headers)


def test_without_id_and_unique_key(spider: Spider) -> None:
    """A request without an id or unique key converts, preserving its user data."""
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
    """An explicit `apify_request_unique_key` in `meta` becomes the Apify request's unique key."""
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
    """A non-Scrapy-request input returns None instead of raising."""
    scrapy_request = 'invalid_request'

    apify_request = to_apify_request(scrapy_request, spider)  # ty: ignore[invalid-argument-type]
    assert apify_request is None


def test_non_json_serializable_meta_is_skipped(spider: Spider, caplog: pytest.LogCaptureFixture) -> None:
    """A non-JSON-serializable value in `meta` is skipped (returns None) and logged, not crashing the crawl."""
    scrapy_request = Request(url='https://example.com', meta={'tags': {'a', 'b'}})

    with caplog.at_level(logging.ERROR, logger='apify.scrapy.requests'):
        apify_request = to_apify_request(scrapy_request, spider)

    assert apify_request is None
    assert any('JSON-serializable' in record.getMessage() for record in caplog.records)


def test_roundtrip_follow_up_request_with_propagated_userdata(spider: Spider) -> None:
    """Regression: propagating userData across repeated roundtrips must not fail on `__crawlee` data."""
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


def test_does_not_mutate_spider_request_user_data(spider: Spider) -> None:
    """Conversion must not mutate the spider's own `meta['userData']` by injecting Crawlee internals."""
    user_data = {'some_user_data': 'test'}
    scrapy_request = Request(url='https://example.com', meta={'userData': user_data})

    to_apify_request(scrapy_request, spider)

    assert user_data == {'some_user_data': 'test'}
    assert '__crawlee' not in user_data


def test_serialized_request_omits_injected_crawlee_data(spider: Spider) -> None:
    """The stored `scrapy_request` blob must not embed the `__crawlee` data `Request.from_url()` injects."""
    scrapy_request = Request(url='https://example.com', meta={'userData': {'some_user_data': 'test'}})

    apify_request = to_apify_request(scrapy_request, spider)
    assert apify_request is not None

    stored = json.loads(cast('str', apify_request.user_data['scrapy_request']))
    assert '__crawlee' not in stored['meta'].get('userData', {})


def test_dont_filter_request_is_always_enqueued(spider: Spider) -> None:
    """A `dont_filter=True` request is always enqueued: each conversion gets a fresh unique key, bypassing dedup."""
    first = to_apify_request(Request(url='https://example.com', dont_filter=True), spider)
    second = to_apify_request(Request(url='https://example.com', dont_filter=True), spider)

    assert first is not None
    assert second is not None
    # `always_enqueue` prefixes the unique key with a random token (`<random>|<key>`), so two otherwise-identical
    # requests get distinct unique keys and neither is deduplicated against the other.
    assert '|' in first.unique_key
    assert first.unique_key != second.unique_key


def test_apify_request_id_in_meta_is_ignored(spider: Spider) -> None:
    """An `apify_request_id` in `meta` is ignored and does not break conversion; the unique key still applies."""
    scrapy_request = Request(
        url='https://example.com',
        meta={'apify_request_id': 'myCustomId12345', 'apify_request_unique_key': 'https://example.com'},
    )

    apify_request = to_apify_request(scrapy_request, spider)

    assert apify_request is not None
    assert apify_request.unique_key == 'https://example.com'
