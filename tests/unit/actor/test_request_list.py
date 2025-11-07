from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, get_args
from unittest.mock import Mock

import pytest
from yarl import URL

from crawlee._request import UserData
from crawlee._types import HttpMethod

from apify.request_loaders import ApifyRequestList
from apify.request_loaders._apify_request_list import URL_NO_COMMAS_REGEX

if TYPE_CHECKING:
    from pytest_httpserver import HTTPServer
    from werkzeug import Request, Response


@pytest.mark.parametrize(
    argnames='request_method',
    argvalues=[
        pytest.param(
            method,
            id=str(method),
        )
        for method in get_args(HttpMethod)
    ],
)
@pytest.mark.parametrize(
    argnames='optional_input',
    argvalues=[
        pytest.param({}, id='minimal'),
        pytest.param(
            {
                'payload': 'some payload',
                'userData': {'some key': 'some value'},
                'headers': {'h1': 'v1', 'h2': 'v2'},
            },
            id='all_options',
        ),
    ],
)
async def test_request_list_open_request_types(
    request_method: HttpMethod,
    optional_input: dict[str, Any],
) -> None:
    """Test proper request list generation from both minimal and full inputs for all method types for simple input."""
    minimal_request_dict_input = {
        'url': 'https://www.abc.com',
        'method': request_method,
    }
    request_dict_input = {**minimal_request_dict_input, **optional_input}

    request_list = await ApifyRequestList.open(request_list_sources_input=[request_dict_input])
    assert not await request_list.is_empty()

    request = await request_list.fetch_next_request()
    assert request is not None
    assert await request_list.is_empty(), 'Request list should be empty after fetching all requests'

    assert request.method == request_dict_input['method']
    assert request.url == request_dict_input['url']
    assert request.payload == request_dict_input.get('payload', '').encode('utf-8')
    expected_user_data = UserData()
    if 'userData' in optional_input:
        for key, value in optional_input['userData'].items():
            expected_user_data[key] = value
    assert request.user_data == expected_user_data
    assert request.headers.root == optional_input.get('headers', {})


async def test_request_list_open_from_url_correctly_send_requests(httpserver: HTTPServer) -> None:
    """Test that requests are sent to expected urls."""
    request_list_sources_input: list[dict[str, Any]] = [
        {
            'requestsFromUrl': httpserver.url_for('/file.txt'),
            'method': 'GET',
        },
        {
            'requestsFromUrl': httpserver.url_for('/file2'),
            'method': 'PUT',
        },
        {
            'requestsFromUrl': httpserver.url_for('/something'),
            'method': 'POST',
            'headers': {'key': 'value'},
            'payload': 'some_payload',
            'userData': {'another_key': 'another_value'},
        },
    ]

    routes: dict[str, Mock] = {}

    def request_handler(request: Request, response: Response) -> Response:
        routes[request.url]()
        return response

    for entry in request_list_sources_input:
        path = str(URL(entry['requestsFromUrl']).path)
        httpserver.expect_oneshot_request(path).with_post_hook(request_handler).respond_with_data(status=200)
        routes[entry['requestsFromUrl']] = Mock()

    await ApifyRequestList.open(request_list_sources_input=request_list_sources_input)

    assert len(routes) == len(request_list_sources_input)

    for entity in request_list_sources_input:
        entity_url = entity['requestsFromUrl']
        assert entity_url in routes
        assert routes[entity_url].called


async def test_request_list_open_from_url(httpserver: HTTPServer) -> None:
    """Test that create_request_list is correctly reading urls from remote url sources and also from simple input."""
    expected_simple_url = 'https://www.someurl.com'
    expected_remote_urls_1 = {'http://www.something.com', 'https://www.somethingelse.com', 'http://www.bla.net'}
    expected_remote_urls_2 = {'http://www.ok.com', 'https://www.true-positive.com'}
    expected_urls = expected_remote_urls_1 | expected_remote_urls_2 | {expected_simple_url}

    @dataclass
    class MockedUrlInfo:
        url: str
        response_text: str

    mocked_urls = (
        MockedUrlInfo(
            httpserver.url_for('/file.txt'),
            'blablabla{} more blablabla{} , even more blablabla. {} '.format(*expected_remote_urls_1),
        ),
        MockedUrlInfo(
            httpserver.url_for('/file2'),
            'some stuff{} more stuff{} www.false_positive.com'.format(*expected_remote_urls_2),
        ),
    )

    request_list_sources_input = [
        {
            'requestsFromUrl': mocked_urls[0].url,
            'method': 'GET',
        },
        {'url': expected_simple_url, 'method': 'GET'},
        {
            'requestsFromUrl': mocked_urls[1].url,
            'method': 'GET',
        },
    ]
    for mocked_url in mocked_urls:
        path = str(URL(mocked_url.url).path)
        httpserver.expect_oneshot_request(path).respond_with_data(status=200, response_data=mocked_url.response_text)

    request_list = await ApifyRequestList.open(request_list_sources_input=request_list_sources_input)
    generated_requests = []
    while request := await request_list.fetch_next_request():
        generated_requests.append(request)

    # Check correctly created requests' urls in request list
    assert {generated_request.url for generated_request in generated_requests} == expected_urls


async def test_request_list_open_from_url_additional_inputs(httpserver: HTTPServer) -> None:
    """Test that all generated request properties are correctly populated from input values."""
    expected_url = 'https://www.someurl.com'
    example_start_url_input: dict[str, Any] = {
        'requestsFromUrl': httpserver.url_for('/file.txt'),
        'method': 'POST',
        'headers': {'key': 'value'},
        'payload': 'some_payload',
        'userData': {'another_key': 'another_value'},
    }
    httpserver.expect_oneshot_request('/file.txt').respond_with_data(status=200, response_data=expected_url)

    request_list = await ApifyRequestList.open(request_list_sources_input=[example_start_url_input])
    request = await request_list.fetch_next_request()
    # Check all properties correctly created for request
    assert request
    assert request.url == expected_url
    assert request.method == example_start_url_input['method']
    assert request.headers.root == example_start_url_input['headers']
    assert request.payload == str(example_start_url_input['payload']).encode('utf-8')
    expected_user_data = UserData()
    for key, value in example_start_url_input['userData'].items():
        expected_user_data[key] = value
    assert request.user_data == expected_user_data


async def test_request_list_open_name() -> None:
    name = 'some_name'
    request_list = await ApifyRequestList.open(name=name)
    assert request_list.name == name


@pytest.mark.parametrize(
    argnames='true_positive',
    argvalues=[
        pytest.param('http://www.something.com', id='standard_http_with_www'),
        pytest.param('https://www.something.net', id='standard_https_with_www'),
        pytest.param('http://nowww.cz', id='http_no_www'),
        pytest.param('https://with-hyphen.com', id='https_with_hyphen'),
        pytest.param('http://number1.com', id='http_with_number_in_domain'),
        pytest.param('http://www.number.123.abc', id='http_with_subdomains_and_numbers'),
        pytest.param('http://many.dots.com', id='http_with_multiple_subdomains'),
        pytest.param('http://a.com', id='http_short_domain'),
        pytest.param('http://www.something.com/somethignelse', id='http_with_path_no_extension'),
        pytest.param('http://www.something.com/somethignelse.txt', id='http_with_path_and_extension'),
        pytest.param('http://non-english-chars-áíéåü.com', id='http_with_non_english_chars'),
        pytest.param('http://www.port.com:1234', id='http_with_port'),
        pytest.param('http://username:password@something.else.com', id='http_with_authentication'),
    ],
)
def test_url_no_commas_regex_true_positives(true_positive: str) -> None:
    example_string = f'Some text {true_positive} some more text'
    matches = list(re.finditer(URL_NO_COMMAS_REGEX, example_string))
    assert len(matches) == 1
    assert matches[0].group(0) == true_positive


@pytest.mark.parametrize(
    argnames='false_positive',
    argvalues=[
        pytest.param('http://www.a', id='invalid_domain_single_level'),
        pytest.param('http://a', id='invalid_domain_no_tld'),
        pytest.param('http://a.a', id='invalid_domain_short_tld'),
        pytest.param('http://123.456', id='invalid_numeric_domain'),
        pytest.param('www.something.com', id='missing_protocol'),
        pytest.param('http:www.something.com', id='missing_slashes'),
    ],
)
def test_url_no_commas_regex_false_positives(false_positive: str) -> None:
    example_string = f'Some text {false_positive} some more text'
    matches = list(re.findall(URL_NO_COMMAS_REGEX, example_string))
    assert len(matches) == 0


def test_url_no_commas_regex_multi_line() -> None:
    true_positives = ('http://www.something.com', 'http://www.else.com')
    example_string = 'Some text {} some more text \n Some new line text {} ...'.format(*true_positives)
    matches = list(re.finditer(URL_NO_COMMAS_REGEX, example_string))
    assert len(matches) == 2
    assert {match.group(0) for match in matches} == set(true_positives)
