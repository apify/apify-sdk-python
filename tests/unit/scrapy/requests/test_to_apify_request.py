from __future__ import annotations

from dataclasses import dataclass

import pytest
from scrapy import Request, Spider

from apify.scrapy.requests import to_apify_request


class DummySpider(Spider):
    name = 'dummy_spider'


@pytest.fixture()
def spider() -> DummySpider:
    """Fixture to create a "dummy" Scrapy spider."""
    return DummySpider()


@dataclass(frozen=True)
class TestCase:
    scrapy_request: Request
    expected_apify_request: dict | None
    expected_exception: type[Exception] | None


test_cases = [
    # Valid Scrapy request with 'apify_request_id' and 'apify_request_unique_key'
    TestCase(
        scrapy_request=Request(
            url='https://example.com',
            method='GET',
            meta={'apify_request_id': 'abc123', 'apify_request_unique_key': 'https://example.com'},
        ),
        expected_apify_request={
            'url': 'https://example.com',
            'method': 'GET',
            'id': 'abc123',
            'uniqueKey': 'https://example.com',
            'userData': {'scrapy_request': 'gANjCg...'},  # Example base64-encoded pickle data
        },
        expected_exception=None,
    ),
    # Valid Scrapy request without 'apify_request_id' and 'apify_request_unique_key'
    TestCase(
        scrapy_request=Request(url='https://apify.com', method='GET'),
        expected_apify_request={
            'url': 'https://apify.com',
            'method': 'GET',
            'userData': {'scrapy_request': 'fhSnfa...'},  # Example base64-encoded pickle data
        },
        expected_exception=None,
    ),
    # Invalid Scrapy request (not an instance of scrapy.Request)
    TestCase(
        scrapy_request=Spider(name='invalid_request'),  # Not a valid Scrapy request
        expected_apify_request=None,
        expected_exception=TypeError,
    ),
]


@pytest.mark.parametrize('tc', test_cases)
def test__to_apify_request(spider: Spider, tc: TestCase) -> None:
    if tc.expected_exception:
        with pytest.raises(tc.expected_exception):
            to_apify_request(tc.scrapy_request, spider)

    else:
        apify_request = to_apify_request(tc.scrapy_request, spider)
        assert isinstance(apify_request, dict)
        assert tc.expected_apify_request is not None
        assert apify_request.get('url') == tc.expected_apify_request.get('url')
        assert apify_request.get('method') == tc.expected_apify_request.get('method')
