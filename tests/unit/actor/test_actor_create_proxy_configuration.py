from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

from apify_client import ApifyClientAsync
from apify_shared.consts import ApifyEnvVars

from apify import Actor

if TYPE_CHECKING:
    from pytest_httpserver import HTTPServer
    from werkzeug import Request, Response

    from ..conftest import ApifyClientAsyncPatcher

DUMMY_PASSWORD = 'DUMMY_PASSWORD'


@pytest.fixture
def patched_apify_client(apify_client_async_patcher: ApifyClientAsyncPatcher) -> ApifyClientAsync:
    apify_client_async_patcher.patch('user', 'get', return_value={'proxy': {'password': DUMMY_PASSWORD}})
    return ApifyClientAsync()


@pytest.mark.usefixtures('patched_impit_client')
async def test_basic_proxy_configuration_creation(
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

    groups = ['GROUP1', 'GROUP2']
    country_code = 'US'

    await Actor.init()

    proxy_configuration = await Actor.create_proxy_configuration(groups=groups, country_code=country_code)

    assert proxy_configuration is not None
    assert proxy_configuration._groups == groups
    assert proxy_configuration._password == DUMMY_PASSWORD
    assert proxy_configuration._country_code == country_code

    assert len(patched_apify_client.calls['user']['get']) == 1  # type: ignore[attr-defined]
    assert call_mock.call_count == 1

    await Actor.exit()


@pytest.mark.usefixtures('patched_impit_client')
async def test_proxy_configuration_with_actor_proxy_input(
    monkeypatch: pytest.MonkeyPatch,
    httpserver: HTTPServer,
    patched_apify_client: ApifyClientAsync,
) -> None:
    dummy_proxy_status_url = str(httpserver.url_for('/')).removesuffix('/')
    dummy_proxy_url = 'http://dummy-proxy.com:8000'

    monkeypatch.setenv(ApifyEnvVars.TOKEN.value, 'DUMMY_TOKEN')
    monkeypatch.setenv(ApifyEnvVars.PROXY_STATUS_URL.value, dummy_proxy_status_url)

    call_mock = Mock()

    def request_handler(request: Request, response: Response) -> Response:
        call_mock(request.url)
        return response

    httpserver.expect_request('/').with_post_hook(request_handler).respond_with_json(
        {
            'connected': True,
            'connectionError': None,
            'isManInTheMiddle': True,
        },
        status=200,
    )

    await Actor.init()

    proxy_configuration = await Actor.create_proxy_configuration(actor_proxy_input={})
    assert proxy_configuration is None

    proxy_configuration = await Actor.create_proxy_configuration(
        actor_proxy_input={
            'useApifyProxy': False,
        }
    )
    assert proxy_configuration is None

    proxy_configuration = await Actor.create_proxy_configuration(
        actor_proxy_input={
            'proxyUrls': [],
        }
    )
    assert proxy_configuration is None

    proxy_configuration = await Actor.create_proxy_configuration(
        actor_proxy_input={
            'useApifyProxy': False,
            'proxyUrls': [dummy_proxy_url],
        }
    )
    assert proxy_configuration is not None
    assert await proxy_configuration.new_url() == dummy_proxy_url

    proxy_configuration = await Actor.create_proxy_configuration(
        actor_proxy_input={
            'useApifyProxy': True,
        }
    )
    assert proxy_configuration is not None
    assert await proxy_configuration.new_url() == f'http://auto:{DUMMY_PASSWORD}@proxy.apify.com:8000'

    groups = ['GROUP1', 'GROUP2']
    country_code = 'US'
    proxy_configuration = await Actor.create_proxy_configuration(
        actor_proxy_input={
            'useApifyProxy': True,
            'apifyProxyGroups': groups,
            'apifyProxyCountry': country_code,
        }
    )
    assert proxy_configuration is not None
    assert (
        await proxy_configuration.new_url()
        == f'http://groups-{"+".join(groups)},country-{country_code}:{DUMMY_PASSWORD}@proxy.apify.com:8000'
    )

    assert len(patched_apify_client.calls['user']['get']) == 2  # type: ignore[attr-defined]
    assert call_mock.call_count == 2

    await Actor.exit()
