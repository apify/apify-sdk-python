from __future__ import annotations

import binascii

import pytest
from scrapy import Request, Spider

from crawlee._types import HttpHeaders

from apify import Request as ApifyRequest
from apify.scrapy.requests import to_scrapy_request


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
        id='fvwscO2UJLdr10B',
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
        id='fvwscO2UJLdr10B',
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


def test_with_reconstruction(spider: Spider) -> None:
    # With reconstruction of encoded Scrapy request
    apify_request = ApifyRequest(
        url='https://apify.com',
        method='GET',
        id='fvwscO2UJLdr10B',
        unique_key='https://apify.com',
        user_data={
            'scrapy_request': 'gASVJgIAAAAAAAB9lCiMA3VybJSMEWh0dHBzOi8vYXBpZnkuY29tlIwIY2FsbGJhY2uUTowHZXJy\nYmFja5ROjAdoZWFkZXJzlH2UKEMGQWNjZXB0lF2UQz90ZXh0L2h0bWwsYXBwbGljYXRpb24veGh0\nbWwreG1sLGFwcGxpY2F0aW9uL3htbDtxPTAuOSwqLyo7cT0wLjiUYUMPQWNjZXB0LUxhbmd1YWdl\nlF2UQwJlbpRhQwpVc2VyLUFnZW50lF2UQyNTY3JhcHkvMi4xMS4wICgraHR0cHM6Ly9zY3JhcHku\nb3JnKZRhQw9BY2NlcHQtRW5jb2RpbmeUXZRDDWd6aXAsIGRlZmxhdGWUYXWMBm1ldGhvZJSMA0dF\nVJSMBGJvZHmUQwCUjAdjb29raWVzlH2UjARtZXRhlH2UKIwQYXBpZnlfcmVxdWVzdF9pZJSMD2Z2\nd3NjTzJVSkxkcjEwQpSMGGFwaWZ5X3JlcXVlc3RfdW5pcXVlX2tleZSMEWh0dHBzOi8vYXBpZnku\nY29tlIwQZG93bmxvYWRfdGltZW91dJRHQGaAAAAAAACMDWRvd25sb2FkX3Nsb3SUjAlhcGlmeS5j\nb22UjBBkb3dubG9hZF9sYXRlbmN5lEc/tYIIAAAAAHWMCGVuY29kaW5nlIwFdXRmLTiUjAhwcmlv\ncml0eZRLAIwLZG9udF9maWx0ZXKUiYwFZmxhZ3OUXZSMCWNiX2t3YXJnc5R9lHUu\n',  # noqa: E501
        },
    )

    scrapy_request = to_scrapy_request(apify_request, spider)

    assert isinstance(scrapy_request, Request)
    assert apify_request.url == scrapy_request.url
    assert apify_request.method == scrapy_request.method
    assert apify_request.unique_key == scrapy_request.meta.get('apify_request_unique_key')
    assert apify_request.user_data == scrapy_request.meta.get('userData')


def test_with_reconstruction_with_optional_fields(spider: Spider) -> None:
    # With reconstruction of encoded Scrapy request
    apify_request = ApifyRequest(
        url='https://apify.com',
        method='GET',
        id='fvwscO2UJLdr10B',
        unique_key='https://apify.com',
        headers=HttpHeaders({'Authorization': 'Bearer access_token'}),
        user_data={
            'some_user_data': 'hello',
            'scrapy_request': 'gASVJgIAAAAAAAB9lCiMA3VybJSMEWh0dHBzOi8vYXBpZnkuY29tlIwIY2FsbGJhY2uUTowHZXJy\nYmFja5ROjAdoZWFkZXJzlH2UKEMGQWNjZXB0lF2UQz90ZXh0L2h0bWwsYXBwbGljYXRpb24veGh0\nbWwreG1sLGFwcGxpY2F0aW9uL3htbDtxPTAuOSwqLyo7cT0wLjiUYUMPQWNjZXB0LUxhbmd1YWdl\nlF2UQwJlbpRhQwpVc2VyLUFnZW50lF2UQyNTY3JhcHkvMi4xMS4wICgraHR0cHM6Ly9zY3JhcHku\nb3JnKZRhQw9BY2NlcHQtRW5jb2RpbmeUXZRDDWd6aXAsIGRlZmxhdGWUYXWMBm1ldGhvZJSMA0dF\nVJSMBGJvZHmUQwCUjAdjb29raWVzlH2UjARtZXRhlH2UKIwQYXBpZnlfcmVxdWVzdF9pZJSMD2Z2\nd3NjTzJVSkxkcjEwQpSMGGFwaWZ5X3JlcXVlc3RfdW5pcXVlX2tleZSMEWh0dHBzOi8vYXBpZnku\nY29tlIwQZG93bmxvYWRfdGltZW91dJRHQGaAAAAAAACMDWRvd25sb2FkX3Nsb3SUjAlhcGlmeS5j\nb22UjBBkb3dubG9hZF9sYXRlbmN5lEc/tYIIAAAAAHWMCGVuY29kaW5nlIwFdXRmLTiUjAhwcmlv\ncml0eZRLAIwLZG9udF9maWx0ZXKUiYwFZmxhZ3OUXZSMCWNiX2t3YXJnc5R9lHUu\n',  # noqa: E501
        },
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


def test_invalid_request_for_reconstruction(spider: Spider) -> None:
    apify_request = ApifyRequest(
        url='https://example.com',
        method='GET',
        id='invalid123',
        unique_key='https://example.com',
        user_data={
            'scrapy_request': 'this is not a correctly encoded Scrapy request',
        },
    )

    with pytest.raises(binascii.Error):
        to_scrapy_request(apify_request, spider)
