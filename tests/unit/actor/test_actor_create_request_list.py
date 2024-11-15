from __future__ import annotations

import typing
from unittest import mock
from unittest.mock import call

import pytest

from crawlee._request import UserData  #  TODO: Make public in Crawlee?
from crawlee._types import HttpHeaders, HttpMethod  #  TODO: Make public in Crawlee?
from crawlee.http_clients import HttpResponse, HttpxHttpClient

from apify import Actor


@pytest.mark.parametrize('request_method', typing.get_args(HttpMethod))
@pytest.mark.parametrize(
    'optional_input',
    [
        {},
        {'payload': 'some payload', 'user_data': {'some key': 'some value'}, 'headers': {'h1': 'v1', 'h2': 'v2'}},
    ],
    ids=['minimal', 'all_options'],
)
async def test_actor_create_request_list_request_types(
    request_method: HttpMethod, optional_input: dict[str, typing.Any]
) -> None:
    """Test proper request list generation from both minimal and full inputs for all method types for simple input."""
    minimal_request_dict_input = {'url': 'https://www.abc.com', 'method': request_method}
    request_dict_input = {**minimal_request_dict_input, **optional_input}
    example_start_urls_input = [
        request_dict_input,
    ]

    generated_request_list = await Actor.create_request_list(actor_start_urls_input=example_start_urls_input)

    assert not await generated_request_list.is_empty()
    generated_request = await generated_request_list.fetch_next_request()
    assert generated_request is not None
    assert await generated_request_list.is_empty()

    assert generated_request.method == request_dict_input['method']
    assert generated_request.url == request_dict_input['url']
    assert generated_request.payload == request_dict_input.get('payload', '').encode('utf-8')
    expected_user_data = UserData()
    if 'user_data' in optional_input:
        for key, value in optional_input['user_data'].items():
            expected_user_data[key] = value
    assert generated_request.user_data == expected_user_data
    expected_headers = HttpHeaders(root=optional_input.get('headers', {}))
    assert generated_request.headers == expected_headers


def _create_dummy_response(read_output: typing.Iterator[str]) -> HttpResponse:
    """Create dummy_response that will iterate through read_output when called like dummy_response.read()"""

    class DummyResponse(HttpResponse):
        @property
        def http_version(self) -> str:
            return ''

        @property
        def status_code(self) -> int:
            return 200

        @property
        def headers(self) -> HttpHeaders:
            return HttpHeaders()

        def read(self) -> bytes:
            return next(read_output).encode('utf-8')

    return DummyResponse()


async def test_actor_create_request_list_from_url_correctly_send_requests() -> None:
    """Test that injected HttpClient's method send_request is called with properly passed arguments."""

    example_start_urls_input: list[dict[str, typing.Any]] = [
        {'requests_from_url': 'https://crawlee.dev/file.txt', 'method': 'GET'},
        {'requests_from_url': 'https://www.crawlee.dev/file2', 'method': 'PUT'},
        {
            'requests_from_url': 'https://www.something.som',
            'method': 'POST',
            'headers': {'key': 'value'},
            'payload': 'some_payload',
            'user_data': {'another_key': 'another_value'},
        },
    ]
    mocked_read_outputs = ('' for url in example_start_urls_input)
    http_client = HttpxHttpClient()
    with mock.patch.object(
        http_client, 'send_request', return_value=_create_dummy_response(mocked_read_outputs)
    ) as mocked_send_request:
        await Actor.create_request_list(actor_start_urls_input=example_start_urls_input, http_client=http_client)

    expected_calls = [
        call(
            method=example_input['method'],
            url=example_input['requests_from_url'],
            headers=example_input.get('headers', {}),
            payload=example_input.get('payload', '').encode('utf-8'),
        )
        for example_input in example_start_urls_input
    ]
    mocked_send_request.assert_has_calls(expected_calls)


async def test_actor_create_request_list_from_url() -> None:
    """Test that create_request_list is correctly reading urls from remote url sources and also from simple input."""
    expected_simple_url = 'https://www.someurl.com'
    expected_remote_urls_1 = {'http://www.something.com', 'https://www.somethingelse.com', 'http://www.bla.net'}
    expected_remote_urls_2 = {'http://www.ok.com', 'https://www.true-positive.com'}
    expected_urls = expected_remote_urls_1 | expected_remote_urls_2 | {expected_simple_url}
    response_bodies = iter(
        (
            'blablabla{} more blablabla{} , even more blablabla. {} '.format(*expected_remote_urls_1),
            'some stuff{} more stuff{} www.falsepositive www.false_positive.com'.format(*expected_remote_urls_2),
        )
    )

    example_start_urls_input = [
        {'requests_from_url': 'https://crawlee.dev/file.txt', 'method': 'GET'},
        {'url': expected_simple_url, 'method': 'GET'},
        {'requests_from_url': 'https://www.crawlee.dev/file2', 'method': 'GET'},
    ]

    http_client = HttpxHttpClient()
    with mock.patch.object(http_client, 'send_request', return_value=_create_dummy_response(response_bodies)):
        generated_request_list = await Actor.create_request_list(
            actor_start_urls_input=example_start_urls_input, http_client=http_client
        )
        generated_requests = []
        while request := await generated_request_list.fetch_next_request():
            print(request)
            generated_requests.append(request)

    # Check correctly created requests' urls in request list
    assert {generated_request.url for generated_request in generated_requests} == expected_urls
