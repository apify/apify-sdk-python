from __future__ import annotations

import binascii
import codecs
import json
import pickle

import pytest
from scrapy import Request, Spider

from crawlee._types import HttpHeaders

from apify import Request as ApifyRequest
from apify.scrapy.requests import _encode_for_json, to_apify_request, to_scrapy_request


class DummySpider(Spider):
    name = 'dummy_spider'


@pytest.fixture
def spider() -> DummySpider:
    """Fixture to create a "dummy" Scrapy spider."""
    return DummySpider()


# JSON-encoded (safe) fixture matching the previous pickle-encoded test data.
_SCRAPY_REQUEST_JSON_ENCODED = (
    'eyJ1cmwiOiJodHRwczovL2FwaWZ5LmNvbSIsImNhbGxiYWNrIjpudWxsLCJlcnJiYWNrIjpudWxs'
    'LCJoZWFkZXJzIjp7IkFjY2VwdCI6W3siX19iNjRfXyI6ImRHVjRkQzlvZEcxc0xHRndjR3hwWTJG'
    'MGFXOXVMM2hvZEcxc0szaHRiQ3hoY0hCc2FXTmhkR2x2Ymk5NGJXdzdjVDB3TGprc0tpOHFPM0U5'
    'TUM0NCJ9XSwiQWNjZXB0LUxhbmd1YWdlIjpbeyJfX2I2NF9fIjoiWlc0PSJ9XSwiVXNlci1BZ2Vu'
    'dCI6W3siX19iNjRfXyI6IlUyTnlZWEI1THpJdU1URXVNQ0FvSzJoMGRIQnpPaTh2YzJOeVlYQjVM'
    'bTl5WnlrPSJ9XSwiQWNjZXB0LUVuY29kaW5nIjpbeyJfX2I2NF9fIjoiWjNwcGNDd2daR1ZtYkdG'
    'MFpRPT0ifV19LCJtZXRob2QiOiJHRVQiLCJib2R5Ijp7Il9fYjY0X18iOiIifSwiY29va2llcyI6'
    'e30sIm1ldGEiOnsiYXBpZnlfcmVxdWVzdF9pZCI6ImZ2d3NjTzJVSkxkcjEwQiIsImFwaWZ5X3Jl'
    'cXVlc3RfdW5pcXVlX2tleSI6Imh0dHBzOi8vYXBpZnkuY29tIiwiZG93bmxvYWRfdGltZW91dCI6'
    'MTgwLjAsImRvd25sb2FkX3Nsb3QiOiJhcGlmeS5jb20iLCJkb3dubG9hZF9sYXRlbmN5IjowLjA4'
    'Mzk4MTk5MDgxNDIwODk4fSwiZW5jb2RpbmciOiJ1dGYtOCIsInByaW9yaXR5IjowLCJkb250X2Zp'
    'bHRlciI6ZmFsc2UsImZsYWdzIjpbXSwiY2Jfa3dhcmdzIjp7fX0=\n'
)


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


def test_with_reconstruction(spider: Spider) -> None:
    # With reconstruction of JSON-encoded Scrapy request
    apify_request = ApifyRequest(
        url='https://apify.com',
        method='GET',
        unique_key='https://apify.com',
        user_data={
            'scrapy_request': _SCRAPY_REQUEST_JSON_ENCODED,
        },
    )

    scrapy_request = to_scrapy_request(apify_request, spider)

    assert isinstance(scrapy_request, Request)
    assert apify_request.url == scrapy_request.url
    assert apify_request.method == scrapy_request.method
    assert apify_request.unique_key == scrapy_request.meta.get('apify_request_unique_key')
    assert apify_request.user_data == scrapy_request.meta.get('userData')


def test_with_reconstruction_with_optional_fields(spider: Spider) -> None:
    # With reconstruction of JSON-encoded Scrapy request
    apify_request = ApifyRequest(
        url='https://apify.com',
        method='GET',
        unique_key='https://apify.com',
        headers=HttpHeaders({'Authorization': 'Bearer access_token'}),
        user_data={
            'some_user_data': 'hello',
            'scrapy_request': _SCRAPY_REQUEST_JSON_ENCODED,
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
        unique_key='https://example.com',
        user_data={
            'scrapy_request': 'this is not a correctly encoded Scrapy request',
        },
    )

    with pytest.raises(binascii.Error):
        to_scrapy_request(apify_request, spider)


def test_pickle_payload_rejected(spider: Spider) -> None:
    """Verify that a pickle-serialized payload is rejected (CWE-502 mitigation).

    Previously, scrapy_request data was serialized with pickle, which allows
    arbitrary code execution when deserializing untrusted data from the
    Apify Request Queue. The new implementation uses JSON and must reject
    pickle payloads.
    """
    # Build a pickle payload (like the old code produced)
    scrapy_request_dict = {
        'url': 'https://evil.com',
        'callback': None,
        'errback': None,
        'headers': {},
        'method': 'GET',
        'body': b'',
        'cookies': {},
        'meta': {},
        'encoding': 'utf-8',
        'priority': 0,
        'dont_filter': False,
        'flags': [],
        'cb_kwargs': {},
    }
    pickle_encoded = codecs.encode(pickle.dumps(scrapy_request_dict), 'base64').decode()

    apify_request = ApifyRequest(
        url='https://evil.com',
        method='GET',
        unique_key='https://evil.com',
        user_data={'scrapy_request': pickle_encoded},
    )

    # The new JSON-based deserialization must reject the pickle payload
    with pytest.raises((json.JSONDecodeError, UnicodeDecodeError, ValueError)):
        to_scrapy_request(apify_request, spider)


def test_roundtrip_serialization(spider: Spider) -> None:
    """Verify that to_apify_request -> to_scrapy_request roundtrip works with JSON encoding."""
    original_request = Request(
        url='https://example.com/test',
        method='POST',
        body=b'test body content',
        headers={'Content-Type': 'application/json', 'X-Custom': 'value'},
        meta={'userData': {'custom_key': 'custom_value'}},
    )

    apify_request = to_apify_request(original_request, spider)
    assert apify_request is not None

    # Verify the encoded data is valid JSON (not pickle)
    encoded = apify_request.user_data['scrapy_request']
    decoded_bytes = codecs.decode(encoded.encode(), 'base64')
    decoded_json = json.loads(decoded_bytes.decode('utf-8'))
    assert isinstance(decoded_json, dict)
    assert decoded_json['url'] == 'https://example.com/test'

    # Reconstruct the Scrapy request
    restored = to_scrapy_request(apify_request, spider)
    assert isinstance(restored, Request)
    assert restored.url == original_request.url
    assert restored.method == original_request.method
    assert restored.body == original_request.body


def test_no_pickle_in_serialized_output(spider: Spider) -> None:
    """Confirm that to_apify_request never produces pickle-serialized output."""
    scrapy_request = Request(url='https://example.com')
    apify_request = to_apify_request(scrapy_request, spider)
    assert apify_request is not None

    encoded = apify_request.user_data['scrapy_request']
    raw_bytes = codecs.decode(encoded.encode(), 'base64')

    # Pickle protocol 4 starts with b'\x80\x04'; JSON starts with b'{'
    assert not raw_bytes.startswith(b'\x80'), 'Output must not be pickle-serialized'
    # Verify it's valid JSON
    json.loads(raw_bytes.decode('utf-8'))
