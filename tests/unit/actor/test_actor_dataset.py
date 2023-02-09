
import pytest

from apify import Actor
from apify.consts import ApifyEnvVars
from apify.memory_storage import MemoryStorage

# NOTE: We only test the dataset methond available on Actor class/instance. Actual tests for the implementations are in storages/.


class TestActorOpenDataset:

    async def test_throws_without_init(self) -> None:
        with pytest.raises(RuntimeError):
            await Actor.open_dataset()

    async def test_same_references(self) -> None:
        async with Actor:
            dataset1 = await Actor.open_dataset()
            dataset2 = await Actor.open_dataset()
            assert dataset1 is dataset2
            dataset_name = 'non-default'
            dataset_named1 = await Actor.open_dataset(name=dataset_name)
            dataset_named2 = await Actor.open_dataset(name=dataset_name)
            assert dataset_named1 is dataset_named2

    async def test_open_datatset_based_env_var(
        self,
        monkeypatch: pytest.MonkeyPatch,
        memory_storage: MemoryStorage,
    ) -> None:
        default_dataset_name = 'my-new-default-name'
        await memory_storage.datasets().get_or_create(name=default_dataset_name)
        monkeypatch.setenv(ApifyEnvVars.DEFAULT_DATASET_ID, default_dataset_name)
        async with Actor:
            ddt = await Actor.open_dataset()
            assert ddt._name == default_dataset_name
            await memory_storage.dataset(ddt._id).delete()


class TestActorPushData:

    async def test_push_data(self) -> None:
        async with Actor() as my_actor:
            dataset = await my_actor.open_dataset()
            desired_item_count = 100
            await dataset.push_data([{'id': i} for i in range(desired_item_count)])
            dataset_info = await dataset.get_info()
            assert dataset_info is not None
            list_page = await dataset.get_data(limit=desired_item_count)
            assert list_page.items[0]['id'] == 0
            assert list_page.items[-1]['id'] == desired_item_count - 1
