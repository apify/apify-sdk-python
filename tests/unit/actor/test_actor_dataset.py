from __future__ import annotations

import pytest

from apify import Actor


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

        dataset_1_metadata = await dataset_by_name_1.get_metadata()
        dataset_by_id_1 = await Actor.open_dataset(id=dataset_1_metadata.id)
        dataset_by_id_2 = await Actor.open_dataset(id=dataset_1_metadata.id)

        assert dataset_by_id_1 is dataset_by_name_1
        assert dataset_by_id_2 is dataset_by_id_1


async def test_push_data_to_dataset() -> None:
    async with Actor as actor:
        dataset = await actor.open_dataset()
        desired_item_count = 100
        await dataset.push_data([{'id': i} for i in range(desired_item_count)])

        list_page = await dataset.get_data(limit=desired_item_count)
        assert {item['id'] for item in list_page.items} == set(range(desired_item_count))
