from __future__ import annotations

from dataclasses import dataclass

import pytest
from scrapy import Request, Spider

from apify.scrapy.utils import to_scrapy_request


class DummySpider(Spider):
    name = 'dummy_spider'


@pytest.fixture()
def spider() -> DummySpider:
    """Fixture to create a "dummy" Scrapy spider."""
    return DummySpider()


@dataclass(frozen=True)
class TestCase:
    apify_request: dict
    expected_scrapy_request: Request
    expected_exception: type[Exception] | None


test_cases = [
    # Valid Apify request without 'userData' (directly from Request Queue)
    TestCase(
        apify_request={'url': 'https://apify.com/', 'method': 'GET', 'uniqueKey': 'https://apify.com/', 'id': 'fvwscO2UJLdr10B'},
        expected_scrapy_request=Request(
            url='https://apify.com/',
            method='GET',
            meta={'apify_request_id': 'fvwscO2UJLdr10B', 'apify_request_unique_key': 'https://apify.com/'},
        ),
        expected_exception=None,
    ),
    # Valid Apify request with 'userData' (reconstruction from encoded Scrapy request)
    TestCase(
        apify_request={
            'url': 'https://apify.com',
            'method': 'GET',
            'id': 'fvwscO2UJLdr10B',
            'uniqueKey': 'https://apify.com',
            'userData': {
                'scrapy_request': 'gASVJgIAAAAAAAB9lCiMA3VybJSMEWh0dHBzOi8vYXBpZnkuY29tlIwIY2FsbGJhY2uUTowHZXJy\nYmFja5ROjAdoZWFkZXJzlH2UKEMGQWNjZXB0lF2UQz90ZXh0L2h0bWwsYXBwbGljYXRpb24veGh0\nbWwreG1sLGFwcGxpY2F0aW9uL3htbDtxPTAuOSwqLyo7cT0wLjiUYUMPQWNjZXB0LUxhbmd1YWdl\nlF2UQwJlbpRhQwpVc2VyLUFnZW50lF2UQyNTY3JhcHkvMi4xMS4wICgraHR0cHM6Ly9zY3JhcHku\nb3JnKZRhQw9BY2NlcHQtRW5jb2RpbmeUXZRDDWd6aXAsIGRlZmxhdGWUYXWMBm1ldGhvZJSMA0dF\nVJSMBGJvZHmUQwCUjAdjb29raWVzlH2UjARtZXRhlH2UKIwQYXBpZnlfcmVxdWVzdF9pZJSMD2Z2\nd3NjTzJVSkxkcjEwQpSMGGFwaWZ5X3JlcXVlc3RfdW5pcXVlX2tleZSMEWh0dHBzOi8vYXBpZnku\nY29tlIwQZG93bmxvYWRfdGltZW91dJRHQGaAAAAAAACMDWRvd25sb2FkX3Nsb3SUjAlhcGlmeS5j\nb22UjBBkb3dubG9hZF9sYXRlbmN5lEc/tYIIAAAAAHWMCGVuY29kaW5nlIwFdXRmLTiUjAhwcmlv\ncml0eZRLAIwLZG9udF9maWx0ZXKUiYwFZmxhZ3OUXZSMCWNiX2t3YXJnc5R9lHUu\n',  # noqa: E501
            },
        },
        expected_scrapy_request=Request(
            url='https://apify.com',
            method='GET',
            meta={'apify_request_id': 'fvwscO2UJLdr10B', 'apify_request_unique_key': 'https://apify.com'},
        ),
        expected_exception=None,
    ),
    # Invalid Apify request (missing 'url' key)
    TestCase(
        apify_request={'method': 'GET', 'id': 'invalid123', 'uniqueKey': 'https://invalid.com'},
        expected_scrapy_request=None,
        expected_exception=ValueError,
    ),
    # Invalid Apify request (missing 'id' key)
    TestCase(
        apify_request={'url': 'https://example.com', 'method': 'GET', 'uniqueKey': 'invalid123'},
        expected_scrapy_request=None,
        expected_exception=ValueError,
    ),
    # Invalid Apify request (non-string 'userData.scrapy_request')
    TestCase(
        apify_request={
            'url': 'https://example.com',
            'method': 'GET',
            'id': 'invalid123',
            'uniqueKey': 'https://example.com',
            'userData': {'scrapy_request': 123},
        },
        expected_scrapy_request=None,
        expected_exception=TypeError,
    ),
]


@pytest.mark.parametrize('tc', test_cases)
def test__to_scrapy_request(spider: Spider, tc: TestCase) -> None:
    if tc.expected_exception:
        with pytest.raises(tc.expected_exception):
            to_scrapy_request(tc.apify_request, spider)

    else:
        scrapy_request = to_scrapy_request(tc.apify_request, spider)

        assert isinstance(scrapy_request, Request)
        assert scrapy_request.url == tc.expected_scrapy_request.url
        assert scrapy_request.method == tc.expected_scrapy_request.method

        # Check meta fields
        assert scrapy_request.meta.get('apify_request_id') == tc.expected_scrapy_request.meta.get('apify_request_id')
        assert scrapy_request.meta.get('apify_request_unique_key') == tc.expected_scrapy_request.meta.get('apify_request_unique_key')

        # Check if meta field is updated properly when apify_request comes from Scrapy
        if 'userData' in tc.apify_request and 'scrapy_request' in tc.apify_request['userData']:
            assert scrapy_request.meta['apify_request_id'] == tc.apify_request['id']
            assert scrapy_request.meta['apify_request_unique_key'] == tc.apify_request['uniqueKey']
