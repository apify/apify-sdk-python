# ruff: noqa: ARG001 ARG005

from __future__ import annotations

import asyncio
import re
from dataclasses import asdict
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

import pytest

from apify_client import ApifyClientAsync
from apify_shared.consts import ApifyEnvVars

from apify._proxy_configuration import ProxyConfiguration, is_url

if TYPE_CHECKING:
    from pytest_httpserver import HTTPServer
    from werkzeug import Request, Response

    from .conftest import ApifyClientAsyncPatcher

DUMMY_PASSWORD = 'DUMMY_PASSWORD'


@pytest.fixture
def patched_apify_client(apify_client_async_patcher: ApifyClientAsyncPatcher) -> ApifyClientAsync:
    apify_client_async_patcher.patch(
        'user',
        'get',
        return_value={
            'proxy': {
                'password': DUMMY_PASSWORD,
            },
        },
    )
    return ApifyClientAsync()


def test_basic_constructor() -> None:
    groups = ['GROUP1', 'GROUP2']
    password = 'abcd1234'
    country_code = 'US'
    proxy_configuration = ProxyConfiguration(
        groups=groups,
        password=password,
        country_code=country_code,
    )
    assert proxy_configuration._groups == groups
    assert proxy_configuration._password == password
    assert proxy_configuration._country_code == country_code


def test_fallback_constructor(monkeypatch: pytest.MonkeyPatch) -> None:
    hostname = 'example.com'
    password = 'abcd1234'
    port = 1234

    monkeypatch.setenv('APIFY_PROXY_HOSTNAME', hostname)
    monkeypatch.setenv('APIFY_PROXY_PASSWORD', password)
    monkeypatch.setenv('APIFY_PROXY_PORT', f'{port}')

    proxy_configuration = ProxyConfiguration()

    assert proxy_configuration._hostname == hostname
    assert proxy_configuration._password == password
    assert proxy_configuration._port == port


def test_invalid_arguments() -> None:
    for invalid_groups, bad_group_index in [
        (['abc', 'de-f', 'geh'], 1),
        (['', 'def', 'geh'], 0),
        (['abc', 'DEF', 'geh$'], 2),
        ([111, 'DEF', 'geh$'], 2),
    ]:
        bad_group = str(invalid_groups[bad_group_index])  # type: ignore[index]

        # Match the actual error message pattern that includes the value and argument name
        match_pattern = f'Value {re.escape(bad_group)} of argument groups does not match pattern'

        with pytest.raises(ValueError, match=match_pattern):
            ProxyConfiguration(groups=invalid_groups)  # type: ignore[arg-type]

    for invalid_country_code in ['CZE', 'aa', 'DDDD', 1111]:
        match_pattern = f'Value {re.escape(str(invalid_country_code))} of argument country_code does not match pattern'
        with pytest.raises(ValueError, match=match_pattern):
            ProxyConfiguration(country_code=invalid_country_code)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match=r'Exactly one of .* must be specified'):
        ProxyConfiguration(
            proxy_urls=['http://proxy.com:1111'],
            new_url_function=lambda session_id=None, request=None: 'http://proxy.com:2222',
        )

    with pytest.raises(ValueError, match=r'Cannot combine custom proxies with Apify Proxy'):
        ProxyConfiguration(proxy_urls=['http://proxy.com:1111'], groups=['GROUP1'])

    with pytest.raises(ValueError, match=re.escape('bad-url')):
        ProxyConfiguration(proxy_urls=['bad-url'])

    with pytest.raises(ValueError, match=r'Cannot combine custom proxies with Apify Proxy'):
        ProxyConfiguration(
            new_url_function=lambda session_id=None, request=None: 'http://proxy.com:2222', groups=['GROUP1']
        )


async def test_new_url_basic() -> None:
    groups = ['GROUP1', 'GROUP2']
    password = 'abcd1234'
    country_code = 'US'
    proxy_configuration = ProxyConfiguration(
        groups=groups,
        password=password,
        country_code=country_code,
    )
    proxy_url = await proxy_configuration.new_url()

    expected_username = f'groups-{"+".join(groups)},country-{country_code}'
    expected_hostname = 'proxy.apify.com'
    expected_port = 8000

    assert proxy_url == f'http://{expected_username}:{password}@{expected_hostname}:{expected_port}'


async def test_new_url_with_session_ids() -> None:
    groups = ['GROUP1', 'GROUP2']
    password = 'abcd1234'
    country_code = 'US'
    proxy_configuration = ProxyConfiguration(
        groups=groups,
        password=password,
        country_code=country_code,
    )

    session_ids: list[str] = [
        'a',
        'a_b',
        'a_2',
        'a_1_b',
        'aaa~BBB',
        '1',
        '0.34252352',
        '123456',
        'XXXXXXXXXXxxxxxxxxxxXXXXXXXXXXxxxxxxxxxxXXXXXXXXXX',
    ]
    for session_id in session_ids:
        expected_username = f'groups-{"+".join(groups)},session-{session_id},country-{country_code}'
        expected_hostname = 'proxy.apify.com'
        expected_port = 8000

        proxy_url = await proxy_configuration.new_url(session_id)

        assert proxy_url == f'http://{expected_username}:{password}@{expected_hostname}:{expected_port}'

    for invalid_session_id in ['a-b', 'a$b', 'XXXXXXXXXXxxxxxxxxxxXXXXXXXXXXxxxxxxxxxxXXXXXXXXXXTooLong']:
        with pytest.raises(ValueError, match=re.escape(str(invalid_session_id))):
            await proxy_configuration.new_url(invalid_session_id)


async def test_rotating_custom_urls() -> None:
    proxy_urls: list[str | None] = ['http://proxy.com:1111', 'http://proxy.com:2222', 'http://proxy.com:3333']
    proxy_configuration = ProxyConfiguration(proxy_urls=proxy_urls)

    assert await proxy_configuration.new_url() == proxy_urls[0]
    assert await proxy_configuration.new_url() == proxy_urls[1]
    assert await proxy_configuration.new_url() == proxy_urls[2]
    assert await proxy_configuration.new_url() == proxy_urls[0]
    assert await proxy_configuration.new_url() == proxy_urls[1]
    assert await proxy_configuration.new_url() == proxy_urls[2]


async def test_rotating_custom_urls_with_sessions() -> None:
    sessions = ['session_01', 'session_02', 'session_03', 'session_04', 'session_05', 'session_06']
    proxy_urls: list[str | None] = ['http://proxy.com:1111', 'http://proxy.com:2222', 'http://proxy.com:3333']

    proxy_configuration = ProxyConfiguration(proxy_urls=proxy_urls)

    # same session should use same proxy URL
    assert await proxy_configuration.new_url(sessions[0]) == proxy_urls[0]
    assert await proxy_configuration.new_url(sessions[0]) == proxy_urls[0]
    assert await proxy_configuration.new_url(sessions[0]) == proxy_urls[0]

    # different sessions should rotate different proxies
    assert await proxy_configuration.new_url(sessions[1]) == proxy_urls[1]
    assert await proxy_configuration.new_url(sessions[2]) == proxy_urls[2]
    assert await proxy_configuration.new_url(sessions[3]) == proxy_urls[0]
    assert await proxy_configuration.new_url(sessions[4]) == proxy_urls[1]
    assert await proxy_configuration.new_url(sessions[5]) == proxy_urls[2]

    # already used sessions should be remembered
    assert await proxy_configuration.new_url(sessions[1]) == proxy_urls[1]
    assert await proxy_configuration.new_url(sessions[3]) == proxy_urls[0]


async def test_with_custom_new_url_function() -> None:
    custom_urls = [
        'http://proxy.com:1111',
        'http://proxy.com:2222',
        'http://proxy.com:3333',
        'http://proxy.com:4444',
        'http://proxy.com:5555',
        'http://proxy.com:6666',
    ]

    def custom_new_url_function(session_id: str | None = None, request: Any = None) -> str:
        nonlocal custom_urls
        return custom_urls.pop()

    proxy_configuration = ProxyConfiguration(new_url_function=custom_new_url_function)

    for custom_url in reversed(custom_urls):
        assert await proxy_configuration.new_url() == custom_url


async def test_with_async_custom_new_url_function() -> None:
    custom_urls = [
        'http://proxy.com:1111',
        'http://proxy.com:2222',
        'http://proxy.com:3333',
        'http://proxy.com:4444',
        'http://proxy.com:5555',
        'http://proxy.com:6666',
    ]

    async def custom_new_url_function(session_id: str | None = None, request: Any = None) -> str:
        nonlocal custom_urls
        await asyncio.sleep(0.1)
        return custom_urls.pop()

    proxy_configuration = ProxyConfiguration(new_url_function=custom_new_url_function)

    for custom_url in reversed(custom_urls):
        assert await proxy_configuration.new_url() == custom_url


async def test_invalid_custom_new_url_function() -> None:
    def custom_new_url_function(session_id: str | None = None, request: Any = None) -> str:
        raise ValueError

    proxy_configuration = ProxyConfiguration(new_url_function=custom_new_url_function)

    with pytest.raises(ValueError, match=r'The provided "new_url_function" did not return a valid URL'):
        await proxy_configuration.new_url()


async def test_url_reference_not_shared_between_instances() -> None:
    proxy_urls: list[str | None] = [
        'http://proxy-example-1.com:8000',
        'http://proxy-example-2.com:8000',
    ]
    proxy_configuration_1 = ProxyConfiguration(proxy_urls=proxy_urls)

    proxy_urls.append('http://proxy-example-3.com:8000')
    proxy_configuration_2 = ProxyConfiguration(proxy_urls=proxy_urls)

    assert proxy_configuration_1 is not None
    assert proxy_configuration_2 is not None

    assert proxy_configuration_1._proxy_urls is not proxy_configuration_2._proxy_urls

    session_id = 'ABCD'
    await proxy_configuration_1.new_url(session_id=session_id)
    await proxy_configuration_2.new_url(session_id=session_id)

    assert proxy_configuration_1._used_proxy_urls is not proxy_configuration_2._used_proxy_urls


async def test_new_proxy_info_basic_construction() -> None:
    groups = ['GROUP1', 'GROUP2']
    password = 'abcd1234'
    country_code = 'US'
    proxy_configuration = ProxyConfiguration(
        groups=groups,
        password=password,
        country_code=country_code,
    )

    proxy_info = await proxy_configuration.new_proxy_info()
    assert proxy_info is not None

    expected_hostname = 'proxy.apify.com'
    expected_port = 8000
    expected_username = f'groups-{"+".join(groups)},country-{country_code}'

    assert asdict(proxy_info) == {
        'url': f'http://{expected_username}:{password}@{expected_hostname}:{expected_port}',
        'hostname': expected_hostname,
        'port': expected_port,
        'groups': groups,
        'country_code': country_code,
        'username': expected_username,
        'password': password,
        'proxy_tier': None,
        'session_id': None,
        'scheme': 'http',
    }


async def test_new_proxy_info_rotating_urls() -> None:
    proxy_urls: list[str | None] = ['http://proxy.com:1111', 'http://proxy.com:2222', 'http://proxy.com:3333']
    proxy_configuration = ProxyConfiguration(proxy_urls=proxy_urls)

    proxy_info = await proxy_configuration.new_proxy_info()
    assert proxy_info is not None
    assert proxy_info.url == proxy_urls[0]

    proxy_info = await proxy_configuration.new_proxy_info()
    assert proxy_info is not None
    assert proxy_info.url == proxy_urls[1]

    proxy_info = await proxy_configuration.new_proxy_info()
    assert proxy_info is not None
    assert proxy_info.url == proxy_urls[2]

    proxy_info = await proxy_configuration.new_proxy_info()
    assert proxy_info is not None
    assert proxy_info.url == proxy_urls[0]

    proxy_info = await proxy_configuration.new_proxy_info()
    assert proxy_info is not None
    assert proxy_info.url == proxy_urls[1]

    proxy_info = await proxy_configuration.new_proxy_info()
    assert proxy_info is not None
    assert proxy_info.url == proxy_urls[2]


async def test_new_proxy_info_rotating_urls_with_sessions() -> None:
    sessions = ['session_01', 'session_02', 'session_03', 'session_04', 'session_05', 'session_06']
    proxy_urls: list[str | None] = ['http://proxy.com:1111', 'http://proxy.com:2222', 'http://proxy.com:3333']

    proxy_configuration = ProxyConfiguration(proxy_urls=proxy_urls)

    # same session should use same proxy URL
    proxy_info = await proxy_configuration.new_proxy_info(sessions[0])
    assert proxy_info is not None
    assert proxy_info.url == proxy_urls[0]

    proxy_info = await proxy_configuration.new_proxy_info(sessions[0])
    assert proxy_info is not None
    assert proxy_info.url == proxy_urls[0]

    proxy_info = await proxy_configuration.new_proxy_info(sessions[0])
    assert proxy_info is not None
    assert proxy_info.url == proxy_urls[0]

    # different sessions should rotate different proxies
    proxy_info = await proxy_configuration.new_proxy_info(sessions[1])
    assert proxy_info is not None
    assert proxy_info.url == proxy_urls[1]

    proxy_info = await proxy_configuration.new_proxy_info(sessions[2])
    assert proxy_info is not None
    assert proxy_info.url == proxy_urls[2]

    proxy_info = await proxy_configuration.new_proxy_info(sessions[3])
    assert proxy_info is not None
    assert proxy_info.url == proxy_urls[0]

    proxy_info = await proxy_configuration.new_proxy_info(sessions[4])
    assert proxy_info is not None
    assert proxy_info.url == proxy_urls[1]

    proxy_info = await proxy_configuration.new_proxy_info(sessions[5])
    assert proxy_info is not None
    assert proxy_info.url == proxy_urls[2]

    # already used sessions should be remembered
    proxy_info = await proxy_configuration.new_proxy_info(sessions[1])
    assert proxy_info is not None
    assert proxy_info.url == proxy_urls[1]

    proxy_info = await proxy_configuration.new_proxy_info(sessions[3])
    assert proxy_info is not None
    assert proxy_info.url == proxy_urls[0]


@pytest.mark.usefixtures('patched_impit_client')
async def test_initialize_with_valid_configuration(
    monkeypatch: pytest.MonkeyPatch,
    httpserver: HTTPServer,
    patched_apify_client: ApifyClientAsync,
) -> None:
    dummy_proxy_status_url = str(httpserver.url_for('/')).removesuffix('/')
    monkeypatch.setenv(ApifyEnvVars.TOKEN.value, 'DUMMY_TOKEN')
    monkeypatch.setenv(ApifyEnvVars.PROXY_STATUS_URL.value, dummy_proxy_status_url)

    call_mock = Mock()

    def request_handler(request: Request, response: Response) -> Response:
        call_mock(request.url)
        return response

    httpserver.expect_oneshot_request('/').with_post_hook(request_handler).respond_with_json(
        {
            'connected': True,
            'connectionError': None,
            'isManInTheMiddle': True,
        },
        status=200,
    )

    proxy_configuration = ProxyConfiguration(_apify_client=patched_apify_client)

    await proxy_configuration.initialize()

    assert proxy_configuration._password == DUMMY_PASSWORD
    assert proxy_configuration.is_man_in_the_middle is True

    assert len(patched_apify_client.calls['user']['get']) == 1  # type: ignore[attr-defined]
    assert call_mock.call_count == 1


async def test_initialize_without_password_or_token() -> None:
    proxy_configuration = ProxyConfiguration()

    with pytest.raises(ValueError, match=r'Apify Proxy password must be provided'):
        await proxy_configuration.initialize()


@pytest.mark.usefixtures('patched_impit_client')
async def test_initialize_with_manual_password(monkeypatch: pytest.MonkeyPatch, httpserver: HTTPServer) -> None:
    dummy_proxy_status_url = str(httpserver.url_for('/')).removesuffix('/')
    monkeypatch.setenv(ApifyEnvVars.PROXY_STATUS_URL.value, dummy_proxy_status_url)

    httpserver.expect_oneshot_request('/').respond_with_json(
        {
            'connected': True,
            'connectionError': None,
            'isManInTheMiddle': False,
        },
        status=200,
    )

    proxy_configuration = ProxyConfiguration(password=DUMMY_PASSWORD)

    await proxy_configuration.initialize()

    assert proxy_configuration._password == DUMMY_PASSWORD
    assert proxy_configuration.is_man_in_the_middle is False


@pytest.mark.usefixtures('patched_impit_client')
async def test_initialize_preferring_password_from_env_over_calling_api(
    monkeypatch: pytest.MonkeyPatch,
    httpserver: HTTPServer,
    patched_apify_client: ApifyClientAsync,
) -> None:
    dummy_proxy_status_url = str(httpserver.url_for('/')).removesuffix('/')
    monkeypatch.setenv(ApifyEnvVars.PROXY_STATUS_URL.value, dummy_proxy_status_url)
    monkeypatch.setenv(ApifyEnvVars.PROXY_PASSWORD.value, DUMMY_PASSWORD)

    httpserver.expect_oneshot_request('/').respond_with_json(
        {
            'connected': True,
            'connectionError': None,
            'isManInTheMiddle': False,
        },
        status=200,
    )

    proxy_configuration = ProxyConfiguration()

    await proxy_configuration.initialize()

    assert proxy_configuration._password == DUMMY_PASSWORD
    assert proxy_configuration.is_man_in_the_middle is False

    assert len(patched_apify_client.calls['user']['get']) == 0  # type: ignore[attr-defined]


@pytest.mark.usefixtures('patched_impit_client')
async def test_initialize_with_manual_password_different_than_user_one(
    monkeypatch: pytest.MonkeyPatch,
    httpserver: HTTPServer,
    patched_apify_client: ApifyClientAsync,
) -> None:
    dummy_proxy_status_url = str(httpserver.url_for('/')).removesuffix('/')
    different_dummy_password = 'DIFFERENT_DUMMY_PASSWORD'
    monkeypatch.setenv(ApifyEnvVars.TOKEN.value, 'DUMMY_TOKEN')
    monkeypatch.setenv(ApifyEnvVars.PROXY_STATUS_URL.value, dummy_proxy_status_url)
    monkeypatch.setenv(ApifyEnvVars.PROXY_PASSWORD.value, different_dummy_password)

    httpserver.expect_oneshot_request('/').respond_with_json(
        {
            'connected': True,
            'connectionError': None,
            'isManInTheMiddle': True,
        },
        status=200,
    )

    proxy_configuration = ProxyConfiguration(_apify_client=patched_apify_client)

    await proxy_configuration.initialize()

    assert proxy_configuration._password == different_dummy_password
    assert proxy_configuration.is_man_in_the_middle is True


@pytest.mark.usefixtures('patched_impit_client')
async def test_initialize_when_not_connected(monkeypatch: pytest.MonkeyPatch, httpserver: HTTPServer) -> None:
    dummy_connection_error = 'DUMMY_CONNECTION_ERROR'
    dummy_proxy_status_url = str(httpserver.url_for('/')).removesuffix('/')
    monkeypatch.setenv(ApifyEnvVars.PROXY_STATUS_URL.value, dummy_proxy_status_url)

    httpserver.expect_oneshot_request('/').respond_with_json(
        {
            'connected': False,
            'connectionError': dummy_connection_error,
        },
        status=200,
    )

    proxy_configuration = ProxyConfiguration(password=DUMMY_PASSWORD)

    with pytest.raises(ConnectionError, match=dummy_connection_error):
        await proxy_configuration.initialize()


async def test_initialize_when_status_page_unavailable(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, httpserver: HTTPServer
) -> None:
    caplog.set_level('WARNING')
    dummy_proxy_status_url = str(httpserver.url_for('/')).removesuffix('/')
    monkeypatch.setenv(ApifyEnvVars.PROXY_STATUS_URL.value, dummy_proxy_status_url)

    httpserver.expect_oneshot_request('/').respond_with_data(status=500)

    proxy_configuration = ProxyConfiguration(password=DUMMY_PASSWORD)

    await proxy_configuration.initialize()

    assert (
        'Apify Proxy access check timed out. Watch out for errors with status code 407. If you see some, it most likely'
        ' means you do not have access to either all or some of the proxies you are trying to use.'
    ) in caplog.messages


async def test_initialize_with_non_apify_proxy(
    monkeypatch: pytest.MonkeyPatch,
    httpserver: HTTPServer,
    patched_apify_client: ApifyClientAsync,
) -> None:
    dummy_proxy_status_url = str(httpserver.url_for('/')).removesuffix('/')
    monkeypatch.setenv(ApifyEnvVars.PROXY_STATUS_URL.value, dummy_proxy_status_url)

    call_mock = Mock()

    def request_handler(request: Request, response: Response) -> Response:
        call_mock(request.url)
        return response

    httpserver.expect_oneshot_request('/').with_post_hook(request_handler).respond_with_data(status=200)

    proxy_configuration = ProxyConfiguration(proxy_urls=['http://dummy-proxy.com:8000'])

    await proxy_configuration.initialize()

    assert len(patched_apify_client.calls['user']['get']) == 0  # type: ignore[attr-defined]
    assert call_mock.call_count == 0


def test_is_url_validation() -> None:
    assert is_url('http://dummy-proxy.com:8000') is True
    assert is_url('https://example.com') is True
    assert is_url('http://localhost') is True
    assert is_url('https://12.34.56.78') is True
    assert is_url('http://12.34.56.78:9012') is True
    assert is_url('http://::1') is True
    assert is_url('https://2f45:4da6:8f56:af8c:5dce:c1de:14d2:8661') is True

    assert is_url('dummy-proxy.com:8000') is False
    assert is_url('gyfwgfhkjhljkfhdsf') is False
    assert is_url('http://') is False
    assert is_url('http://example') is False
    assert is_url('http:/example.com') is False
    assert is_url('12.34.56.78') is False
    assert is_url('::1') is False
    assert is_url('https://4da6:8f56:af8c:5dce:c1de:14d2:8661') is False
