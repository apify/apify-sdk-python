from __future__ import annotations

from typing import TYPE_CHECKING

from apify_shared.consts import ApifyEnvVars

from .._utils import generate_unique_resource_name
from apify import Actor

if TYPE_CHECKING:
    import pytest

    from apify_client import ApifyClientAsync

    from .conftest import MakeActorFunction, RunActorFunction


async def test_push_and_verify_data_in_default_dataset(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    desired_item_count = 100  # Also change inside main() if you're changing this

    async def main() -> None:
        desired_item_count = 100
        async with Actor:
            await Actor.push_data([{'id': i} for i in range(desired_item_count)])

    actor = await make_actor(label='push-data', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'

    list_page = await actor.last_run().dataset().list_items()
    assert list_page.items[0]['id'] == 0
    assert list_page.items[-1]['id'] == desired_item_count - 1
    assert len(list_page.items) == list_page.count == desired_item_count


async def test_push_large_data_chunks_over_9mb(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        async with Actor:
            await Actor.push_data([{'str': 'x' * 10000} for _ in range(5000)])  # ~50MB

    actor = await make_actor(label='push-data-over-9mb', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'

    async for item in actor.last_run().dataset().iterate_items():
        assert item['str'] == 'x' * 10000


async def test_dataset_iter_items(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        inserted_data = {'Something': 'something else'}

        async with Actor:
            dataset = await Actor.open_dataset()
            await dataset.push_data(inserted_data)
            requested_data = [item async for item in dataset.iterate_items()]

            assert len(requested_data) == 1
            assert requested_data[0] == inserted_data

    actor = await make_actor(label='test_dataset_iter_items', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'


async def test_same_references_in_default_dataset(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        async with Actor:
            dataset1 = await Actor.open_dataset()
            dataset2 = await Actor.open_dataset()
            assert dataset1 is dataset2

    actor = await make_actor(label='dataset-same-ref-default', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_same_references_in_named_dataset(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    dataset_name = generate_unique_resource_name('dataset')

    async def main() -> None:
        async with Actor:
            input_object = await Actor.get_input()
            dataset_name = input_object['datasetName']
            dataset_by_name_1 = await Actor.open_dataset(name=dataset_name)
            dataset_by_name_2 = await Actor.open_dataset(name=dataset_name)
            assert dataset_by_name_1 is dataset_by_name_2

            dataset_1_metadata = await dataset_by_name_1.get_metadata()
            dataset_by_id_1 = await Actor.open_dataset(id=dataset_1_metadata.id)
            dataset_by_id_2 = await Actor.open_dataset(id=dataset_1_metadata.id)
            assert dataset_by_id_1 is dataset_by_name_1
            assert dataset_by_id_2 is dataset_by_id_1

            await dataset_by_name_1.drop()

    actor = await make_actor(label='dataset-same-ref-named', main_func=main)
    run_result = await run_actor(actor, run_input={'datasetName': dataset_name})

    assert run_result.status == 'SUCCEEDED'


async def test_force_cloud(
    apify_client_async: ApifyClientAsync,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert apify_client_async.token is not None
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_client_async.token)

    dataset_name = generate_unique_resource_name('dataset')
    dataset_item = {'foo': 'bar'}

    async with Actor:
        dataset = await Actor.open_dataset(name=dataset_name, force_cloud=True)
        dataset_id = (await dataset.get_metadata()).id

        await dataset.push_data(dataset_item)

    dataset_client = apify_client_async.dataset(dataset_id)

    try:
        dataset_details = await dataset_client.get()
        assert dataset_details is not None
        assert dataset_details.get('name') == dataset_name

        dataset_items = await dataset_client.list_items()
        assert dataset_items.items == [dataset_item]
    finally:
        await dataset_client.delete()


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
