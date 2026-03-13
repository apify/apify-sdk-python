from apify import Actor


async def main() -> None:
    async with Actor:
        assert Actor.configuration.actor_storages
        dataset = await Actor.open_dataset(alias='custom')
        expected_id = Actor.configuration.actor_storages['datasets']['custom']
        assert dataset.id == expected_id

        implicit_default_dataset = await Actor.open_dataset()
        explicit_default_dataset = await Actor.open_dataset(alias='default')
        assert implicit_default_dataset.id == explicit_default_dataset.id
