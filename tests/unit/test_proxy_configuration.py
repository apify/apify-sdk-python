import asyncio
import re
from typing import List, Optional, Union

import httpx
import pytest
from respx import MockRouter

from apify.consts import ApifyEnvVars
from apify.proxy_configuration import ProxyConfiguration
from apify_client import ApifyClientAsync

from .conftest import ApifyClientAsyncPatcher

DUMMY_PASSWORD = 'DUMMY_PASSWORD'


class TestProxyConfiguration:
    def test_constructor_basic(self) -> None:
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

    def test_constructor_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
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

    def test__fails_with_invalid_arguments(self) -> None:
        for (invalid_groups, bad_group_index) in [
            (['abc', 'de-f', 'geh'], 1),
            (['', 'def', 'geh'], 0),
            (['abc', 'DEF', 'geh$'], 2),
            ([111, 'DEF', 'geh$'], 2),
        ]:
            with pytest.raises(ValueError, match=re.escape(str(invalid_groups[bad_group_index]))):  # type: ignore
                ProxyConfiguration(groups=invalid_groups)  # type: ignore

        for invalid_country_code in ['CZE', 'aa', 'DDDD', 1111]:
            with pytest.raises(ValueError, match=re.escape(str(invalid_country_code))):
                ProxyConfiguration(country_code=invalid_country_code)  # type: ignore

        with pytest.raises(ValueError, match='Cannot combine custom proxies in "proxy_urls" with custom generating function in "new_url_function".'):
            ProxyConfiguration(proxy_urls=['http://proxy.com:1111'], new_url_function=lambda _: 'http://proxy.com:2222')

        with pytest.raises(ValueError, match='Cannot combine custom proxies with Apify Proxy'):
            ProxyConfiguration(proxy_urls=['http://proxy.com:1111'], groups=['GROUP1'])

        with pytest.raises(ValueError, match='Cannot combine custom proxies with Apify Proxy'):
            ProxyConfiguration(new_url_function=lambda _: 'http://proxy.com:2222', groups=['GROUP1'])


class TestProxyConfigurationNewUrl:
    @pytest.mark.asyncio
    async def test_new_url_basic(self) -> None:
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

    @pytest.mark.asyncio
    async def test_new_url_session_id(self) -> None:
        groups = ['GROUP1', 'GROUP2']
        password = 'abcd1234'
        country_code = 'US'
        proxy_configuration = ProxyConfiguration(
            groups=groups,
            password=password,
            country_code=country_code,
        )

        session_ids: List[Union[str, int]] = [
            'a', 'a_b', 'a_2', 'a_1_b', 'aaa~BBB',
            '1', '0.34252352', 123456, 'XXXXXXXXXXxxxxxxxxxxXXXXXXXXXXxxxxxxxxxxXXXXXXXXXX',
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

    @pytest.mark.asyncio
    async def test_rotating_custom_urls(self) -> None:
        proxy_urls = ['http://proxy.com:1111', 'http://proxy.com:2222', 'http://proxy.com:3333']
        proxy_configuration = ProxyConfiguration(proxy_urls=proxy_urls)

        assert await proxy_configuration.new_url() == proxy_urls[0]
        assert await proxy_configuration.new_url() == proxy_urls[1]
        assert await proxy_configuration.new_url() == proxy_urls[2]
        assert await proxy_configuration.new_url() == proxy_urls[0]
        assert await proxy_configuration.new_url() == proxy_urls[1]
        assert await proxy_configuration.new_url() == proxy_urls[2]

    @pytest.mark.asyncio
    async def test_rotating_custom_urls_with_sessions(self) -> None:
        sessions = ['sesssion_01', 'sesssion_02', 'sesssion_03', 'sesssion_04', 'sesssion_05', 'sesssion_06']
        proxy_urls = ['http://proxy.com:1111', 'http://proxy.com:2222', 'http://proxy.com:3333']

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

    @pytest.mark.asyncio
    async def test_custom_new_url_function(self) -> None:
        custom_urls = [
            'http://proxy.com:1111', 'http://proxy.com:2222', 'http://proxy.com:3333',
            'http://proxy.com:4444', 'http://proxy.com:5555', 'http://proxy.com:6666',
        ]

        def custom_new_url_function(_session_id: Optional[str]) -> str:
            nonlocal custom_urls
            return custom_urls.pop()

        proxy_configuration = ProxyConfiguration(new_url_function=custom_new_url_function)

        for custom_url in reversed(custom_urls):
            assert await proxy_configuration.new_url() == custom_url

    @pytest.mark.asyncio
    async def test_custom_new_url_function_async(self) -> None:
        custom_urls = [
            'http://proxy.com:1111', 'http://proxy.com:2222', 'http://proxy.com:3333',
            'http://proxy.com:4444', 'http://proxy.com:5555', 'http://proxy.com:6666',
        ]

        async def custom_new_url_function(_session_id: Optional[str]) -> str:
            nonlocal custom_urls
            await asyncio.sleep(0.1)
            return custom_urls.pop()

        proxy_configuration = ProxyConfiguration(new_url_function=custom_new_url_function)

        for custom_url in reversed(custom_urls):
            assert await proxy_configuration.new_url() == custom_url

    @pytest.mark.asyncio
    async def test_invalid_custom_new_url_function(self) -> None:
        def custom_new_url_function(_session_id: Optional[str]) -> str:
            raise ValueError()

        proxy_configuration = ProxyConfiguration(new_url_function=custom_new_url_function)

        with pytest.raises(ValueError, match='The provided "new_url_function" did not return a valid URL'):
            await proxy_configuration.new_url()

    @pytest.mark.asyncio
    async def test_proxy_configuration_not_sharing_references(self) -> None:
        urls = [
            'http://proxy-example-1.com:8000',
            'http://proxy-example-2.com:8000',
        ]
        proxy_configuration_1 = ProxyConfiguration(
            proxy_urls=urls,
        )

        urls.append('http://proxy-example-3.com:8000')
        proxy_configuration_2 = ProxyConfiguration(
            proxy_urls=urls,
        )

        assert proxy_configuration_1 is not None
        assert proxy_configuration_2 is not None

        assert proxy_configuration_1._proxy_urls is not proxy_configuration_2._proxy_urls

        session_id = 'ABCD'
        await proxy_configuration_1.new_url(session_id=session_id)
        await proxy_configuration_2.new_url(session_id=session_id)

        assert proxy_configuration_1._used_proxy_urls is not proxy_configuration_2._proxy_urls


class TestProxyConfigurationNewProxyInfo:
    @pytest.mark.asyncio
    async def test_new_proxy_info_basic(self) -> None:
        groups = ['GROUP1', 'GROUP2']
        password = 'abcd1234'
        country_code = 'US'
        proxy_configuration = ProxyConfiguration(
            groups=groups,
            password=password,
            country_code=country_code,
        )
        proxy_info = await proxy_configuration.new_proxy_info()

        expected_hostname = 'proxy.apify.com'
        expected_port = 8000
        expected_username = f'groups-{"+".join(groups)},country-{country_code}'

        assert proxy_info == {
            'url': f'http://{expected_username}:{password}@{expected_hostname}:{expected_port}',
            'hostname': expected_hostname,
            'port': expected_port,
            'groups': groups,
            'country_code': country_code,
            'username': expected_username,
            'password': password,
        }

    @pytest.mark.asyncio
    async def test_new_proxy_info_rotates_urls(self) -> None:
        proxy_urls = ['http://proxy.com:1111', 'http://proxy.com:2222', 'http://proxy.com:3333']
        proxy_configuration = ProxyConfiguration(proxy_urls=proxy_urls)

        assert (await proxy_configuration.new_proxy_info())['url'] == proxy_urls[0]
        assert (await proxy_configuration.new_proxy_info())['url'] == proxy_urls[1]
        assert (await proxy_configuration.new_proxy_info())['url'] == proxy_urls[2]
        assert (await proxy_configuration.new_proxy_info())['url'] == proxy_urls[0]
        assert (await proxy_configuration.new_proxy_info())['url'] == proxy_urls[1]
        assert (await proxy_configuration.new_proxy_info())['url'] == proxy_urls[2]

    @pytest.mark.asyncio
    async def test_new_proxy_info_rotates_urls_with_sessions(self) -> None:
        sessions = ['sesssion_01', 'sesssion_02', 'sesssion_03', 'sesssion_04', 'sesssion_05', 'sesssion_06']
        proxy_urls = ['http://proxy.com:1111', 'http://proxy.com:2222', 'http://proxy.com:3333']

        proxy_configuration = ProxyConfiguration(proxy_urls=proxy_urls)

        # same session should use same proxy URL
        assert (await proxy_configuration.new_proxy_info(sessions[0]))['url'] == proxy_urls[0]
        assert (await proxy_configuration.new_proxy_info(sessions[0]))['url'] == proxy_urls[0]
        assert (await proxy_configuration.new_proxy_info(sessions[0]))['url'] == proxy_urls[0]

        # different sessions should rotate different proxies
        assert (await proxy_configuration.new_proxy_info(sessions[1]))['url'] == proxy_urls[1]
        assert (await proxy_configuration.new_proxy_info(sessions[2]))['url'] == proxy_urls[2]
        assert (await proxy_configuration.new_proxy_info(sessions[3]))['url'] == proxy_urls[0]
        assert (await proxy_configuration.new_proxy_info(sessions[4]))['url'] == proxy_urls[1]
        assert (await proxy_configuration.new_proxy_info(sessions[5]))['url'] == proxy_urls[2]

        # already used sessions should be remembered
        assert (await proxy_configuration.new_proxy_info(sessions[1]))['url'] == proxy_urls[1]
        assert (await proxy_configuration.new_proxy_info(sessions[3]))['url'] == proxy_urls[0]


@pytest.fixture
def patched_apify_client(apify_client_async_patcher: ApifyClientAsyncPatcher) -> ApifyClientAsync:
    apify_client_async_patcher.patch('user', 'get', return_value={
        'proxy': {
            'password': DUMMY_PASSWORD,
        },
    })

    return ApifyClientAsync()


class TestProxyConfigurationInitialize:
    @pytest.mark.asyncio
    async def test_initialize_basic(
        self,
        monkeypatch: pytest.MonkeyPatch,
        respx_mock: MockRouter,
        patched_apify_client: ApifyClientAsync,
    ) -> None:
        dummy_proxy_status_url = 'http://dummy-proxy-status-url.com'
        monkeypatch.setenv(ApifyEnvVars.TOKEN.value, 'DUMMY_TOKEN')
        monkeypatch.setenv(ApifyEnvVars.PROXY_STATUS_URL.value, dummy_proxy_status_url)

        route = respx_mock.get(dummy_proxy_status_url)
        route.mock(httpx.Response(200, json={
            'connected': True,
            'connectionError': None,
            'isManInTheMiddle': True,
        }))

        proxy_configuration = ProxyConfiguration(apify_client=patched_apify_client)

        await proxy_configuration.initialize()

        assert proxy_configuration._password == DUMMY_PASSWORD
        assert proxy_configuration.is_man_in_the_middle is True

        assert len(patched_apify_client.calls['user']['get']) == 1  # type: ignore
        assert len(route.calls) == 1

    @pytest.mark.asyncio
    async def test_initialize_no_password_no_token(self) -> None:
        proxy_configuration = ProxyConfiguration()

        with pytest.raises(ValueError, match='Apify Proxy password must be provided'):
            await proxy_configuration.initialize()

    @pytest.mark.asyncio
    async def test_initialize_manual_password(
        self,
        monkeypatch: pytest.MonkeyPatch,
        respx_mock: MockRouter,
    ) -> None:
        dummy_proxy_status_url = 'http://dummy-proxy-status-url.com'
        monkeypatch.setenv(ApifyEnvVars.PROXY_STATUS_URL.value, dummy_proxy_status_url)

        respx_mock.get(dummy_proxy_status_url).mock(httpx.Response(200, json={
            'connected': True,
            'connectionError': None,
            'isManInTheMiddle': False,
        }))

        proxy_configuration = ProxyConfiguration(password=DUMMY_PASSWORD)

        await proxy_configuration.initialize()

        assert proxy_configuration._password == DUMMY_PASSWORD
        assert proxy_configuration.is_man_in_the_middle is False

    @pytest.mark.asyncio
    async def test_initialize_manual_password_different_than_user_one(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
        respx_mock: MockRouter,
        patched_apify_client: ApifyClientAsync,
    ) -> None:
        dummy_proxy_status_url = 'http://dummy-proxy-status-url.com'
        different_dummy_password = 'DIFFERENT_DUMMY_PASSWORD'
        monkeypatch.setenv(ApifyEnvVars.TOKEN.value, 'DUMMY_TOKEN')
        monkeypatch.setenv(ApifyEnvVars.PROXY_STATUS_URL.value, dummy_proxy_status_url)
        monkeypatch.setenv(ApifyEnvVars.PROXY_PASSWORD.value, different_dummy_password)

        respx_mock.get(dummy_proxy_status_url).mock(httpx.Response(200, json={
            'connected': True,
            'connectionError': None,
            'isManInTheMiddle': True,
        }))

        proxy_configuration = ProxyConfiguration(apify_client=patched_apify_client)

        await proxy_configuration.initialize()

        assert proxy_configuration._password == different_dummy_password
        assert proxy_configuration.is_man_in_the_middle is True

        out, _ = capsys.readouterr()
        assert 'The Apify Proxy password you provided belongs to a different user' in out

    @pytest.mark.asyncio
    async def test_initialize_not_connected(
        self,
        monkeypatch: pytest.MonkeyPatch,
        respx_mock: MockRouter,
    ) -> None:
        dummy_connection_error = 'DUMMY_CONNECTION_ERROR'
        dummy_proxy_status_url = 'http://dummy-proxy-status-url.com'
        monkeypatch.setenv(ApifyEnvVars.PROXY_STATUS_URL.value, dummy_proxy_status_url)

        respx_mock.get(dummy_proxy_status_url).mock(httpx.Response(200, json={
            'connected': False,
            'connectionError': dummy_connection_error,
        }))

        proxy_configuration = ProxyConfiguration(password=DUMMY_PASSWORD)

        with pytest.raises(ConnectionError, match=dummy_connection_error):
            await proxy_configuration.initialize()

    @pytest.mark.asyncio
    async def test_initialize_status_page_unavailable(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
        respx_mock: MockRouter,
    ) -> None:
        dummy_proxy_status_url = 'http://dummy-proxy-status-url.com'
        monkeypatch.setenv(ApifyEnvVars.PROXY_STATUS_URL.value, dummy_proxy_status_url)

        respx_mock.get(dummy_proxy_status_url).mock(httpx.Response(500))

        proxy_configuration = ProxyConfiguration(password=DUMMY_PASSWORD)

        await proxy_configuration.initialize()

        out, _ = capsys.readouterr()
        assert 'Apify Proxy access check timed out' in out

    @pytest.mark.asyncio
    async def test_initialize_not_called_non_apify_proxy(
        self,
        monkeypatch: pytest.MonkeyPatch,
        respx_mock: MockRouter,
        patched_apify_client: ApifyClientAsync,
    ) -> None:
        dummy_proxy_status_url = 'http://dummy-proxy-status-url.com'
        monkeypatch.setenv(ApifyEnvVars.PROXY_STATUS_URL.value, dummy_proxy_status_url)

        route = respx_mock.get(dummy_proxy_status_url)
        route.mock(httpx.Response(200))

        proxy_configuration = ProxyConfiguration(proxy_urls=['http://dummy-proxy.com:8000'])

        await proxy_configuration.initialize()

        assert len(patched_apify_client.calls['user']['get']) == 0  # type: ignore
        assert len(route.calls) == 0
