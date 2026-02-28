from __future__ import annotations

import binascii

import pytest
from scrapy import Request, Spider

from crawlee._types import HttpHeaders

from apify import Request as ApifyRequest
from apify.scrapy.requests import to_apify_request, to_scrapy_request


class DummySpider(Spider):
    name = 'dummy_spider'


@pytest.fixture
def spider() -> DummySpider:
    """Fixture to create a "dummy" Scrapy spider."""
    return DummySpider()


def test_without_reconstruction(spider: Spider) -> None:
    # Without reconstruction of encoded Scrapy request
    apify_request = ApifyRequest(
        url='https://example.com',
        method='GET',
        unique_key='https://example.com',
        user_data={},
    )

    scrapy_request = to_scrapy_request(apify_request, spider)

    assert isinstance(scrapy_request, Request)
    assert apify_request.url == scrapy_request.url
    assert apify_request.method == scrapy_request.method
    assert apify_request.unique_key == scrapy_request.meta.get('apify_request_unique_key')


def test_without_reconstruction_with_optional_fields(spider: Spider) -> None:
    # Without reconstruction of encoded Scrapy request
    apify_request = ApifyRequest(
        url='https://crawlee.dev',
        method='GET',
        unique_key='https://crawlee.dev',
        headers=HttpHeaders({'Authorization': 'Bearer access_token'}),
        user_data={'some_user_data': 'test'},
    )

    scrapy_request = to_scrapy_request(apify_request, spider)

    assert isinstance(scrapy_request, Request)
    assert apify_request.url == scrapy_request.url
    assert apify_request.method == scrapy_request.method
    assert apify_request.unique_key == scrapy_request.meta.get('apify_request_unique_key')

    scrapy_request_headers = scrapy_request.headers.get('authorization')
    assert scrapy_request_headers is not None
    assert apify_request.headers.get('authorization') == scrapy_request_headers.decode()
    assert apify_request.user_data == scrapy_request.meta.get('userData')


def test_with_reconstruction_roundtrip(spider: Spider) -> None:
    """Test that a Scrapy request survives serialization and deserialization roundtrip."""
    original_scrapy_request = Request(
        url='https://apify.com',
        method='GET',
        meta={
            'apify_request_unique_key': 'https://apify.com',
        },
    )

    apify_request = to_apify_request(original_scrapy_request, spider)
    assert apify_request is not None

    scrapy_request = to_scrapy_request(apify_request, spider)

    assert isinstance(scrapy_request, Request)
    assert apify_request.url == scrapy_request.url
    assert apify_request.method == scrapy_request.method
    assert apify_request.unique_key == scrapy_request.meta.get('apify_request_unique_key')
    assert apify_request.user_data == scrapy_request.meta.get('userData')


def test_with_reconstruction_roundtrip_with_optional_fields(spider: Spider) -> None:
    """Test roundtrip with headers and user data."""
    original_scrapy_request = Request(
        url='https://apify.com',
        method='GET',
        headers={'Authorization': 'Bearer access_token'},
        meta={
            'apify_request_unique_key': 'https://apify.com',
            'userData': {'some_user_data': 'hello'},
        },
    )

    apify_request = to_apify_request(original_scrapy_request, spider)
    assert apify_request is not None
    apify_request.headers = HttpHeaders({'Authorization': 'Bearer access_token'})

    scrapy_request = to_scrapy_request(apify_request, spider)

    assert isinstance(scrapy_request, Request)
    assert apify_request.url == scrapy_request.url
    assert apify_request.method == scrapy_request.method
    assert apify_request.unique_key == scrapy_request.meta.get('apify_request_unique_key')

    scrapy_request_headers = scrapy_request.headers.get('authorization')
    assert scrapy_request_headers is not None
    assert apify_request.headers.get('authorization') == scrapy_request_headers.decode()


def test_invalid_request_for_reconstruction(spider: Spider) -> None:
    apify_request = ApifyRequest(
        url='https://example.com',
        method='GET',
        unique_key='https://example.com',
        user_data={
            'scrapy_request': 'this is not a correctly encoded Scrapy request',
        },
    )

    with pytest.raises(binascii.Error):
        to_scrapy_request(apify_request, spider)
