from __future__ import annotations

from typing import TYPE_CHECKING

from apify import Actor

if TYPE_CHECKING:
    from .conftest import MakeActorFunction, RunActorFunction


async def test_create_basic_proxy_configuration(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
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

    actor = await make_actor(label='proxy-configuration', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_create_proxy_configuration_with_groups_and_country(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        await Actor.init()

        proxy_url_suffix = (
            f'{Actor.configuration.proxy_password}@{Actor.configuration.proxy_hostname}:'
            f'{Actor.configuration.proxy_port}'
        )
        proxy_configuration = await Actor.create_proxy_configuration(actor_proxy_input={'useApifyProxy': True})

        assert proxy_configuration is not None

        new_url = await proxy_configuration.new_url()
        assert new_url == f'http://auto:{proxy_url_suffix}'

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

        new_url = await proxy_configuration.new_url()
        assert new_url == f'http://groups-{"+".join(groups)},country-{country_code}:{proxy_url_suffix}'

        await Actor.exit()

    actor = await make_actor(label='proxy-configuration', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'
