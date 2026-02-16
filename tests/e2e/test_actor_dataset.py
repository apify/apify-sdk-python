from __future__ import annotations

from typing import TYPE_CHECKING

from apify import Actor

if TYPE_CHECKING:
    from .conftest import MakeActorFunction, RunActorFunction


async def test_dataset_defaults(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        from apify.storages import Dataset

        async with Actor:
            was_rebooted = await Actor.get_value('was_rebooted', default_value=False)

            dataset_1 = await Actor.open_dataset()
            dataset_2 = await Dataset.open()

            assert dataset_1 is dataset_2

            if not was_rebooted:
                await dataset_1.push_data({'from': 'dataset_1'})
                await dataset_2.push_data({'from': 'dataset_2'})
                await Actor.set_value('was_rebooted', value=True)
                await Actor.reboot()

            dataset_11 = await Actor.open_dataset()
            dataset_22 = await Dataset.open()

            assert dataset_11 is dataset_22
            assert dataset_1.id == dataset_11.id == dataset_2.id == dataset_22.id

            dataset_1_items = await dataset_11.list_items()
            dataset_2_items = await dataset_22.list_items()

            assert dataset_1_items == [{'from': 'dataset_1'}, {'from': 'dataset_2'}]
            assert dataset_2_items == [{'from': 'dataset_1'}, {'from': 'dataset_2'}]

    actor = await make_actor(label='dataset-defaults', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_dataset_aliases(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        from apify.storages import Dataset

        async with Actor:
            was_rebooted = await Actor.get_value('was_rebooted', default_value=False)

            dataset_1 = await Actor.open_dataset(alias='my-alias-dataset-1')
            dataset_2 = await Dataset.open(alias='my-alias-dataset-2')

            assert dataset_1 is not dataset_2
            assert dataset_1.id != dataset_2.id
            assert dataset_1.name is None
            assert dataset_2.name is None

            if not was_rebooted:
                await dataset_1.push_data({'from': 'dataset_1'})
                await dataset_2.push_data({'from': 'dataset_2'})
                await Actor.set_value('was_rebooted', value=True)
                await Actor.reboot()

            dataset_11 = await Actor.open_dataset(alias='my-alias-dataset-1')
            dataset_22 = await Dataset.open(alias='my-alias-dataset-2')

            assert dataset_1.id == dataset_11.id
            assert dataset_11 is dataset_1

            assert dataset_2.id == dataset_22.id
            assert dataset_22 is dataset_2

            dataset_1_items = await dataset_11.list_items()
            dataset_2_items = await dataset_22.list_items()
            assert dataset_1_items == [{'from': 'dataset_1'}]
            assert dataset_2_items == [{'from': 'dataset_2'}]

    actor = await make_actor(label='dataset-aliases', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'
