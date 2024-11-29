from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest

from apify_client import ApifyClientAsync
from apify_shared.consts import ApifyEnvVars

from apify import Actor

if TYPE_CHECKING:
    from respx import MockRouter

    from ..conftest import ApifyClientAsyncPatcher

DUMMY_PASSWORD = 'DUMMY_PASSWORD'


@pytest.fixture
def patched_apify_client(apify_client_async_patcher: ApifyClientAsyncPatcher) -> ApifyClientAsync:
    apify_client_async_patcher.patch('user', 'get', return_value={'proxy': {'password': DUMMY_PASSWORD}})
    return ApifyClientAsync()


async def test_basic_proxy_configuration_creation(
    monkeypatch: pytest.MonkeyPatch,
    respx_mock: MockRouter,
    patched_apify_client: ApifyClientAsync,
) -> None:
    dummy_proxy_status_url = 'http://dummy-proxy-status-url.com'
    monkeypatch.setenv(ApifyEnvVars.TOKEN.value, 'DUMMY_TOKEN')
    monkeypatch.setenv(ApifyEnvVars.PROXY_STATUS_URL.value, dummy_proxy_status_url)

    route = respx_mock.get(dummy_proxy_status_url)
    route.mock(
        httpx.Response(
            200,
            json={
                'connected': True,
                'connectionError': None,
                'isManInTheMiddle': True,
            },
        )
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
    assert len(route.calls) == 1

    await Actor.exit()


async def test_proxy_configuration_with_actor_proxy_input(
    monkeypatch: pytest.MonkeyPatch,
    respx_mock: MockRouter,
    patched_apify_client: ApifyClientAsync,
) -> None:
    dummy_proxy_status_url = 'http://dummy-proxy-status-url.com'
    dummy_proxy_url = 'http://dummy-proxy.com:8000'

    monkeypatch.setenv(ApifyEnvVars.TOKEN.value, 'DUMMY_TOKEN')
    monkeypatch.setenv(ApifyEnvVars.PROXY_STATUS_URL.value, dummy_proxy_status_url)

    route = respx_mock.get(dummy_proxy_status_url)
    route.mock(
        httpx.Response(
            200,
            json={
                'connected': True,
                'connectionError': None,
                'isManInTheMiddle': True,
            },
        )
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
    assert len(route.calls) == 2

    await Actor.exit()
