from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from apify_shared.consts import ActorEnvVars

from apify import Actor

if TYPE_CHECKING:
    from crawlee.storage_clients import MemoryStorageClient

# NOTE: We only test the dataset methods available on Actor class/instance.
# Actual tests for the implementations are in storages/.


async def test_throws_error_without_actor_init() -> None:
    with pytest.raises(RuntimeError):
        await Actor.open_dataset()


async def test_open_dataset_returns_same_references() -> None:
    async with Actor:
        dataset1 = await Actor.open_dataset()
        dataset2 = await Actor.open_dataset()
        assert dataset1 is dataset2

        dataset_name = 'non-default'
        dataset_by_name_1 = await Actor.open_dataset(name=dataset_name)
        dataset_by_name_2 = await Actor.open_dataset(name=dataset_name)
        assert dataset_by_name_1 is dataset_by_name_2

        dataset_by_id_1 = await Actor.open_dataset(id=dataset_by_name_1._id)
        dataset_by_id_2 = await Actor.open_dataset(id=dataset_by_name_1._id)

        assert dataset_by_id_1 is dataset_by_name_1
        assert dataset_by_id_2 is dataset_by_id_1


async def test_open_dataset_uses_env_var(
    monkeypatch: pytest.MonkeyPatch,
    memory_storage_client: MemoryStorageClient,
) -> None:
    default_dataset_id = 'my-new-default-id'
    monkeypatch.setenv(ActorEnvVars.DEFAULT_DATASET_ID, default_dataset_id)

    async with Actor:
        ddt = await Actor.open_dataset()
        assert ddt._id == default_dataset_id
        await memory_storage_client.dataset(ddt._id).delete()


async def test_push_data_to_dataset() -> None:
    async with Actor as my_actor:
        dataset = await my_actor.open_dataset()
        desired_item_count = 100
        await dataset.push_data([{'id': i} for i in range(desired_item_count)])

        dataset_info = await dataset.get_info()
        assert dataset_info is not None

        list_page = await dataset.get_data(limit=desired_item_count)
        assert {item['id'] for item in list_page.items} == set(range(desired_item_count))
