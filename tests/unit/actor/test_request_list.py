from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, get_args

import pytest
import respx
from httpx import Response

from crawlee._request import UserData
from crawlee._types import HttpMethod

from apify.storages._request_list import URL_NO_COMMAS_REGEX, RequestList


@pytest.mark.parametrize('request_method', get_args(HttpMethod))
@pytest.mark.parametrize(
    'optional_input',
    [
        {},
        {
            'payload': 'some payload',
            'userData': {'some key': 'some value'},
            'headers': {'h1': 'v1', 'h2': 'v2'},
        },
    ],
    ids=['minimal', 'all_options'],
)
async def test_request_list_open_request_types(request_method: HttpMethod, optional_input: dict[str, Any]) -> None:
    """Test proper request list generation from both minimal and full inputs for all method types for simple input."""
    minimal_request_dict_input = {
        'url': 'https://www.abc.com',
        'method': request_method,
    }
    request_dict_input = {**minimal_request_dict_input, **optional_input}

    request_list = await RequestList.open(request_list_sources_input=[request_dict_input])
    assert not await request_list.is_empty()
    request = await request_list.fetch_next_request()
    assert request is not None
    assert await request_list.is_empty()

    assert request.method == request_dict_input['method']
    assert request.url == request_dict_input['url']
    assert request.payload == request_dict_input.get('payload', '').encode('utf-8')
    expected_user_data = UserData()
    if 'userData' in optional_input:
        for key, value in optional_input['userData'].items():
            expected_user_data[key] = value
    assert request.user_data == expected_user_data
    assert request.headers.root == optional_input.get('headers', {})


@respx.mock
async def test_request_list_open_from_url_correctly_send_requests() -> None:
    """Test that requests are sent to expected urls."""
    request_list_sources_input: list[dict[str, Any]] = [
        {
            'requestsFromUrl': 'https://abc.dev/file.txt',
            'method': 'GET',
        },
        {
            'requestsFromUrl': 'https://www.abc.dev/file2',
            'method': 'PUT',
        },
        {
            'requestsFromUrl': 'https://www.something.som',
            'method': 'POST',
            'headers': {'key': 'value'},
            'payload': 'some_payload',
            'userData': {'another_key': 'another_value'},
        },
    ]

    routes = [respx.get(entry['requestsFromUrl']) for entry in request_list_sources_input]

    await RequestList.open(request_list_sources_input=request_list_sources_input)

    for route in routes:
        assert route.called


@respx.mock
async def test_request_list_open_from_url() -> None:
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
            'https://abc.dev/file.txt',
            'blablabla{} more blablabla{} , even more blablabla. {} '.format(*expected_remote_urls_1),
        ),
        MockedUrlInfo(
            'https://www.abc.dev/file2',
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
        respx.get(mocked_url.url).mock(return_value=Response(200, text=mocked_url.response_text))

    request_list = await RequestList.open(request_list_sources_input=request_list_sources_input)
    generated_requests = []
    while request := await request_list.fetch_next_request():
        generated_requests.append(request)

    # Check correctly created requests' urls in request list
    assert {generated_request.url for generated_request in generated_requests} == expected_urls


@respx.mock
async def test_request_list_open_from_url_additional_inputs() -> None:
    """Test that all generated request properties are correctly populated from input values."""
    expected_url = 'https://www.someurl.com'
    example_start_url_input: dict[str, Any] = {
        'requestsFromUrl': 'https://crawlee.dev/file.txt',
        'method': 'POST',
        'headers': {'key': 'value'},
        'payload': 'some_payload',
        'userData': {'another_key': 'another_value'},
    }

    respx.get(example_start_url_input['requestsFromUrl']).mock(return_value=Response(200, text=expected_url))

    request_list = await RequestList.open(request_list_sources_input=[example_start_url_input])
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
    request_list = await RequestList.open(name=name)
    assert request_list.name == name


@pytest.mark.parametrize(
    'true_positive',
    [
        'http://www.something.com',
        'https://www.something.net',
        'http://nowww.cz',
        'https://with-hypen.com',
        'http://number1.com',
        'http://www.number.123.abc',
        'http://many.dots.com',
        'http://a.com',
        'http://www.something.com/somethignelse' 'http://www.something.com/somethignelse.txt',
        'http://non-english-chars-áíéåü.com',
        'http://www.port.com:1234',
        'http://username:password@something.else.com',
    ],
)
def test_url_no_commas_regex_true_positives(true_positive: str) -> None:
    example_string = f'Some text {true_positive} some more text'
    matches = list(re.finditer(URL_NO_COMMAS_REGEX, example_string))
    assert len(matches) == 1
    assert matches[0].group(0) == true_positive


@pytest.mark.parametrize(
    'false_positive',
    [
        'http://www.a',
        'http://a',
        'http://a.a',
        'http://123.456',
        'www.something.com',
        'http:www.something.com',
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