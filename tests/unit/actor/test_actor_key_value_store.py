from apify import Actor

# NOTE: We only test the references here. Actual tests for the implementations are in storages/


async def test_same_references() -> None:
    async with Actor:
        kvs1 = await Actor.open_key_value_store()
        kvs2 = await Actor.open_key_value_store()
        assert kvs1 is kvs2
        kvs_name = 'non-default'
        kvs_named1 = await Actor.open_key_value_store(kvs_name)
        kvs_named2 = await Actor.open_key_value_store(kvs_name)
        assert kvs_named1 is kvs_named2
