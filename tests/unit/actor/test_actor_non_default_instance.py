from datetime import timedelta

from apify import Actor, Configuration


async def test_actor_non_default_instance() -> None:
    async with Actor(Configuration(internal_timeout=timedelta(minutes=111))) as actor:
        assert actor.config.internal_timeout == timedelta(minutes=111)
