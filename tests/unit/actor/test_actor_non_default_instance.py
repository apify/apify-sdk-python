from __future__ import annotations

from datetime import timedelta

from apify import Actor, Configuration


async def test_actor_with_non_default_config() -> None:
    config = Configuration(internal_timeout=timedelta(minutes=111))

    async with Actor(config) as actor:
        assert actor.config.internal_timeout == timedelta(minutes=111)


async def test_actor_global_works() -> None:
    non_default_configuration = Configuration(actor_full_name='Actor McActorson, esq.')

    async with Actor(configuration=non_default_configuration):
        assert Actor.configuration is non_default_configuration
