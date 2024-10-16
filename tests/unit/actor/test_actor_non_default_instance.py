from datetime import timedelta

from apify import Actor, Configuration


async def test_actor_with_non_default_config() -> None:
    config = Configuration(internal_timeout=timedelta(minutes=111))

    async with Actor(config) as actor:
        assert actor.config.internal_timeout == timedelta(minutes=111)
