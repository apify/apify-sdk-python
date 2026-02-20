from apify import Actor


async def main() -> None:
    async with Actor:
        assert Actor.configuration.actor_storages
        assert (await Actor.open_dataset(alias='custom')).id == Actor.configuration.actor_storages['datasets']['custom']
