
from apify import Actor

# NOTE: We only test the references here. Actual tests for the implementations are in storages/

async def test_same_references() -> None:
    async with Actor:
        dataset1 = await Actor.open_dataset()
        dataset2 = await Actor.open_dataset()
        assert dataset1 is dataset2
        dataset_name = 'non-default'
        dataset_named1 = await Actor.open_dataset(dataset_name)
        dataset_named2 = await Actor.open_dataset(dataset_name)
        assert dataset_named1 is dataset_named2
