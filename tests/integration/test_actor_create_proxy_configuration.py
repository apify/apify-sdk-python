from __future__ import annotations

from typing import TYPE_CHECKING

from apify import Actor

if TYPE_CHECKING:
    from apify_client import ApifyClientAsync

    from .conftest import ActorFactory


async def test_create_basic_proxy_configuration(
    apify_client_async: ApifyClientAsync,
    make_actor: ActorFactory,
) -> None:
    async def main() -> None:
        groups = ['SHADER']
        country_code = 'US'

        async with Actor:
            proxy_configuration = await Actor.create_proxy_configuration(
                groups=groups,
                country_code=country_code,
            )

            assert proxy_configuration is not None
            assert proxy_configuration._groups == groups
            assert proxy_configuration._password is not None
            assert proxy_configuration._country_code == country_code

    actor = await make_actor('proxy-configuration', main_func=main)

    call_result = await actor.call()
    assert call_result is not None

    run_client = apify_client_async.run(call_result['id'])
    run_result = await run_client.wait_for_finish(wait_secs=300)

    assert run_result is not None
    assert run_result['status'] == 'SUCCEEDED'


async def test_create_proxy_configuration_with_groups_and_country(
    apify_client_async: ApifyClientAsync,
    make_actor: ActorFactory,
) -> None:
    async def main() -> None:
        await Actor.init()

        proxy_url_suffix = f'{Actor.config.proxy_password}@{Actor.config.proxy_hostname}:{Actor.config.proxy_port}'

        proxy_configuration = await Actor.create_proxy_configuration(
            actor_proxy_input={
                'useApifyProxy': True,
            }
        )
        assert proxy_configuration is not None
        assert await proxy_configuration.new_url() == f'http://auto:{proxy_url_suffix}'

        groups = ['SHADER', 'BUYPROXIES94952']
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
            == f'http://groups-{"+".join(groups)},country-{country_code}:{proxy_url_suffix}'
        )

        await Actor.exit()

    actor = await make_actor('proxy-configuration', main_func=main)

    call_result = await actor.call()
    assert call_result is not None

    run_client = apify_client_async.run(call_result['id'])
    run_result = await run_client.wait_for_finish(wait_secs=300)

    assert run_result is not None
    assert run_result['status'] == 'SUCCEEDED'
