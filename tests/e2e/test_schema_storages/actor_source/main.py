from apify import Actor


async def main() -> None:
    async with Actor:
        assert Actor.configuration.actor_storages
        dataset = await Actor.open_dataset(alias='custom')
        expected_id = Actor.configuration.actor_storages['datasets']['custom']
        assert dataset.id == expected_id
