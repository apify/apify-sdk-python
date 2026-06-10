from __future__ import annotations

import codecs
import json
import pickle
import sys

import pytest
from scrapy import FormRequest, Request, Spider

from crawlee._types import HttpHeaders

from apify import Request as ApifyRequest
from apify.scrapy._serialization import encode_to_json
from apify.scrapy.requests import to_apify_request, to_scrapy_request


class DummySpider(Spider):
    name = 'dummy_spider'


@pytest.fixture
def spider() -> DummySpider:
    """Fixture to create a "dummy" Scrapy spider."""
    return DummySpider()


# A JSON-encoded (pickle-free) Scrapy request for a GET request to https://apify.com, encoded exactly
# the way `to_apify_request` stores it under `user_data['scrapy_request']` (JSON, no outer base64).
_SCRAPY_REQUEST_JSON_ENCODED = encode_to_json(
    {
        'url': 'https://apify.com',
        'callback': None,
        'errback': None,
        'headers': {
            b'Accept': [b'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'],
            b'Accept-Language': [b'en'],
            b'User-Agent': [b'Scrapy/2.11.0 (+https://scrapy.org)'],
            b'Accept-Encoding': [b'gzip, deflate'],
        },
        'body': b'',
        'cookies': {},
        'meta': {'apify_request_id': 'fvwscO2UJLdr10B', 'apify_request_unique_key': 'https://apify.com'},
        'encoding': 'utf-8',
        'flags': [],
        'cb_kwargs': {},
        'dont_filter': False,
        'method': 'GET',
        'priority': 0,
    }
)


def test_without_reconstruction(spider: Spider) -> None:
    """An Apify request without a stored `scrapy_request` becomes a fresh Scrapy request (no reconstruction)."""
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
    """The without-reconstruction path also carries optional headers and user data to the Scrapy request."""
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
    """An Apify request with a stored `scrapy_request` is reconstructed from its JSON payload."""
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
    """Reconstruction from the stored JSON payload also restores optional headers and user data."""
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
    """A stored `scrapy_request` that is not valid JSON fails to decode during reconstruction."""
    apify_request = ApifyRequest(
        url='https://example.com',
        method='GET',
        unique_key='https://example.com',
        user_data={
            'scrapy_request': 'this is not a correctly encoded Scrapy request',
        },
    )

    # The stored value is parsed as JSON directly (no outer base64), so non-JSON text fails to decode.
    with pytest.raises(json.JSONDecodeError):
        to_scrapy_request(apify_request, spider)


def test_pickle_payload_rejected(spider: Spider) -> None:
    """Data under 'scrapy_request' is JSON, so a pickle payload is rejected rather than deserialized."""
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
    """A `to_apify_request` -> `to_scrapy_request` round-trip preserves the request under JSON encoding."""
    original_request = Request(
        url='https://example.com/test',
        method='POST',
        body=b'test body content',
        headers={'Content-Type': 'application/json', 'X-Custom': 'value'},
        meta={'userData': {'custom_key': 'custom_value'}},
    )

    apify_request = to_apify_request(original_request, spider)
    assert apify_request is not None

    # Verify the stored data is JSON (not pickle) and not wrapped in an outer base64 layer.
    encoded = apify_request.user_data['scrapy_request']
    assert isinstance(encoded, str)
    decoded_json = json.loads(encoded)
    assert isinstance(decoded_json, dict)
    assert decoded_json['url'] == 'https://example.com/test'

    # Reconstruct the Scrapy request
    restored = to_scrapy_request(apify_request, spider)
    assert isinstance(restored, Request)
    assert restored.url == original_request.url
    assert restored.method == original_request.method
    assert restored.body == original_request.body


def test_no_pickle_in_serialized_output(spider: Spider) -> None:
    """`to_apify_request` produces JSON output, never a pickle payload."""
    scrapy_request = Request(url='https://example.com')
    apify_request = to_apify_request(scrapy_request, spider)
    assert apify_request is not None

    encoded = apify_request.user_data['scrapy_request']
    assert isinstance(encoded, str)

    # Pickle output starts with the b'\x80' opcode byte; JSON is text starting with '{'.
    assert encoded.lstrip().startswith('{'), 'Output must be JSON, not pickle'
    json.loads(encoded)  # must parse as JSON


def _encode_request_dict(request_dict: dict) -> str:
    """Encode a raw request dict the same way `to_apify_request` does (JSON, no outer base64)."""
    return encode_to_json(request_dict)


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
    """A request with non-UTF-8 header values is not dropped; the exact header bytes survive the roundtrip."""
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
    """No in-band sentinel is used, so a user dict like `{'__b64__': ...}` in `meta` round-trips unchanged."""
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
    """A `_class` resolving to a non-`scrapy.Request` type (here a plain `dict`) is rejected before use."""
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

    with pytest.raises(TypeError, match=r'not a scrapy\.Request subclass'):
        to_scrapy_request(apify_request, spider)


def test_unresolvable_class_is_rejected(spider: Spider) -> None:
    """A `_class` whose dotted path cannot be resolved (no such module) is rejected with a clear error."""
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

    with pytest.raises(TypeError, match='cannot resolve'):
        to_scrapy_request(apify_request, spider)


def test_custom_request_subclass_reconstructed_after_migration(spider: Spider) -> None:
    """Actor-migration case: a not-yet-imported custom `Request` subclass is reconstructed by importing it."""
    module_name = 'tests.unit.scrapy.requests._custom_request_module'
    request_dict = {
        'url': 'https://example.com',
        'callback': None,
        'errback': None,
        'headers': {},
        'body': b'',
        'cookies': {},
        'meta': {},
        'encoding': 'utf-8',
        'priority': 0,
        'dont_filter': False,
        'flags': [],
        'cb_kwargs': {},
        'method': 'GET',
        '_class': f'{module_name}.CustomRequest',
    }
    apify_request = ApifyRequest(
        url='https://example.com',
        method='GET',
        unique_key='https://example.com',
        user_data={'scrapy_request': _encode_request_dict(request_dict)},
    )

    # Simulate a fresh process where the subclass's module has not been imported yet.
    sys.modules.pop(module_name, None)

    restored = to_scrapy_request(apify_request, spider)

    from tests.unit.scrapy.requests._custom_request_module import CustomRequest

    assert isinstance(restored, CustomRequest)
    assert module_name in sys.modules  # it was imported on demand during reconstruction
