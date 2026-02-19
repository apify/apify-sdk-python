from apify import Actor


async def main() -> None:
    async with Actor:
        assert Actor.configuration.actor_storages
        assert (await Actor.open_dataset(alias='custom_d')).id == Actor.configuration.actor_storages.datasets[
            'custom_d'
        ]
        assert (await Actor.open_dataset(alias='custom_kvs')).id == Actor.configuration.actor_storages.datasets[
            'custom_kvs'
        ]
        assert (await Actor.open_dataset(alias='custom_rq')).id == Actor.configuration.actor_storages.datasets[
            'custom_rq'
        ]
