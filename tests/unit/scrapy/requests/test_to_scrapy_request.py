from __future__ import annotations

import binascii
import codecs
import json
import pickle

import pytest
from scrapy import FormRequest, Request, Spider

from crawlee._types import HttpHeaders

from apify import Request as ApifyRequest
from apify.scrapy.requests import to_apify_request, to_scrapy_request


class DummySpider(Spider):
    name = 'dummy_spider'


@pytest.fixture
def spider() -> DummySpider:
    """Fixture to create a "dummy" Scrapy spider."""
    return DummySpider()


# Base64-encoded JSON fixture (the pickle-free format) for a GET request to https://apify.com.
_SCRAPY_REQUEST_JSON_ENCODED = (
    'eyJ1cmwiOiAiaHR0cHM6Ly9hcGlmeS5jb20iLCAiY2FsbGJhY2siOiBudWxsLCAiZXJyYmFjayI6\n'
    'IG51bGwsICJoZWFkZXJzIjogeyJBY2NlcHQiOiBbImRHVjRkQzlvZEcxc0xHRndjR3hwWTJGMGFX\n'
    'OXVMM2hvZEcxc0szaHRiQ3hoY0hCc2FXTmhkR2x2Ymk5NGJXdzdjVDB3TGprc0tpOHFPM0U5TUM0\n'
    'NCJdLCAiQWNjZXB0LUxhbmd1YWdlIjogWyJaVzQ9Il0sICJVc2VyLUFnZW50IjogWyJVMk55WVhC\n'
    'NUx6SXVNVEV1TUNBb0syaDBkSEJ6T2k4dmMyTnlZWEI1TG05eVp5az0iXSwgIkFjY2VwdC1FbmNv\n'
    'ZGluZyI6IFsiWjNwcGNDd2daR1ZtYkdGMFpRPT0iXX0sICJib2R5IjogIiIsICJjb29raWVzIjog'
    'e30sICJtZXRhIjogeyJhcGlmeV9yZXF1ZXN0X2lkIjogImZ2d3NjTzJVSkxkcjEwQiIsICJhcGlm'
    'eV9yZXF1ZXN0X3VuaXF1ZV9rZXkiOiAiaHR0cHM6Ly9hcGlmeS5jb20ifSwgImVuY29kaW5nIjog'
    'InV0Zi04IiwgImZsYWdzIjogW10sICJjYl9rd2FyZ3MiOiB7fSwgImRvbnRfZmlsdGVyIjogZmFs'
    'c2UsICJtZXRob2QiOiAiR0VUIiwgInByaW9yaXR5IjogMH0=\n'
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
    """Data stored under 'scrapy_request' is JSON; a pickle-encoded payload is not valid JSON.

    The reconstruction path must reject such a payload rather than deserialize it.
    """
    # Build a pickle payload like the old code produced.
    scrapy_request_dict = {
        'url': 'https://example.com',
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
        url='https://example.com',
        method='GET',
        unique_key='https://example.com',
        user_data={'scrapy_request': pickle_encoded},
    )

    # The JSON-based reconstruction must reject the pickle payload.
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
    assert isinstance(encoded, str)
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
    assert isinstance(encoded, str)
    raw_bytes = codecs.decode(encoded.encode(), 'base64')

    # Pickle protocol 4 starts with b'\x80\x04'; JSON starts with b'{'
    assert not raw_bytes.startswith(b'\x80'), 'Output must not be pickle-serialized'
    # Verify it's valid JSON
    json.loads(raw_bytes.decode('utf-8'))


def _encode_request_dict(request_dict: dict) -> str:
    """Encode a raw request dict the same way `to_apify_request` does (base64-encoded JSON)."""
    return codecs.encode(json.dumps(request_dict).encode('utf-8'), 'base64').decode()


def test_binary_body_round_trips(spider: Spider) -> None:
    """Non-UTF-8 bytes in the request body survive the JSON roundtrip (base64-encoded)."""
    original = Request(
        url='https://example.com',
        method='POST',
        body=b'\x00\x01\x02\xff\xfe binary',
        headers={'Content-Type': 'application/octet-stream'},
    )

    apify_request = to_apify_request(original, spider)
    assert apify_request is not None

    restored = to_scrapy_request(apify_request, spider)
    assert restored.body == b'\x00\x01\x02\xff\xfe binary'
    assert restored.headers.get('Content-Type') == b'application/octet-stream'


def test_binary_headers_round_trip_and_request_not_dropped(spider: Spider) -> None:
    """A request with non-UTF-8 header values is not dropped; its headers survive the roundtrip.

    The Apify-request-level headers can only hold UTF-8-decodable values, so binary header values are
    preserved inside the serialized Scrapy request instead. The conversion must still succeed (return
    a request, not None) and the exact header bytes must come back.
    """
    original = Request(
        url='https://example.com',
        headers={b'Accept': b'text/html', b'X-Bin': b'\xff\xfe\x00'},
    )

    apify_request = to_apify_request(original, spider)
    assert apify_request is not None  # must not be dropped

    restored = to_scrapy_request(apify_request, spider)
    assert restored.headers.get(b'X-Bin') == b'\xff\xfe\x00'
    assert restored.headers.get(b'Accept') == b'text/html'


def test_userdata_with_b64_sentinel_key_round_trips(spider: Spider) -> None:
    """A user dict that happens to look like a bytes wrapper must round-trip unchanged.

    The encoder uses no in-band sentinel for user data, so an arbitrary value such as
    ``{"__b64__": "..."}`` in `meta` is preserved exactly instead of being reinterpreted.
    """
    original = Request(
        url='https://example.com',
        meta={'userData': {}, 'looks_like_sentinel': {'__b64__': 'not really base64 !!!'}},
    )

    apify_request = to_apify_request(original, spider)
    assert apify_request is not None

    restored = to_scrapy_request(apify_request, spider)
    assert restored.meta['looks_like_sentinel'] == {'__b64__': 'not really base64 !!!'}


def test_already_imported_request_subclass_round_trips(spider: Spider) -> None:
    """A `_class` referring to an already-imported `scrapy.Request` subclass is reconstructed."""
    original = FormRequest(url='https://example.com', formdata={'key': 'value'})

    apify_request = to_apify_request(original, spider)
    assert apify_request is not None

    restored = to_scrapy_request(apify_request, spider)
    assert isinstance(restored, FormRequest)
    assert restored.method == 'POST'


def test_non_request_class_is_rejected(spider: Spider) -> None:
    """A `_class` that resolves to something other than a `scrapy.Request` subclass is rejected.

    `scrapy.utils.request.request_from_dict` resolves `_class` via `load_object`, which imports the
    dotted path it is given. Reconstruction only accepts an already-imported `scrapy.Request`
    subclass; anything else (here a plain `dict`) is rejected.
    """
    request_dict = {
        'url': 'https://example.com',
        'callback': None,
        'errback': None,
        'headers': {},
        'body': '',
        'cookies': {},
        'meta': {},
        'encoding': 'utf-8',
        'priority': 0,
        'dont_filter': False,
        'flags': [],
        'cb_kwargs': {},
        'method': 'GET',
        '_class': 'builtins.dict',
    }
    apify_request = ApifyRequest(
        url='https://example.com',
        method='GET',
        unique_key='https://example.com',
        user_data={'scrapy_request': _encode_request_dict(request_dict)},
    )

    with pytest.raises(TypeError, match='not an already-imported'):
        to_scrapy_request(apify_request, spider)


def test_class_referring_to_unimported_module_is_rejected(spider: Spider) -> None:
    """A `_class` whose module is not already imported is rejected without importing it."""
    request_dict = {
        'url': 'https://example.com',
        'headers': {},
        'body': '',
        'cookies': {},
        'meta': {},
        'encoding': 'utf-8',
        'priority': 0,
        'dont_filter': False,
        'flags': [],
        'cb_kwargs': {},
        'method': 'GET',
        '_class': 'definitely_not_imported_pkg.some_module.SomeRequest',
    }
    apify_request = ApifyRequest(
        url='https://example.com',
        method='GET',
        unique_key='https://example.com',
        user_data={'scrapy_request': _encode_request_dict(request_dict)},
    )

    with pytest.raises(TypeError, match='not an already-imported'):
        to_scrapy_request(apify_request, spider)
