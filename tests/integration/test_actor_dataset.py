import pytest

from apify import Actor
from apify.consts import ApifyEnvVars
from apify_client import ApifyClientAsync

from ._utils import generate_unique_resource_name
from .conftest import ActorFactory


class TestActorPushData:
    async def test_push_data(self, make_actor: ActorFactory) -> None:
        desired_item_count = 100  # Also change inside main() if you're changing this

        async def main() -> None:
            desired_item_count = 100
            async with Actor:
                await Actor.push_data([{'id': i} for i in range(desired_item_count)])

        actor = await make_actor('push-data', main_func=main)

        run_result = await actor.call()

        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'
        list_page = await actor.last_run().dataset().list_items()
        assert list_page.items[0]['id'] == 0
        assert list_page.items[-1]['id'] == desired_item_count - 1
        assert len(list_page.items) == list_page.count == desired_item_count

    async def test_push_data_over_9mb(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            async with Actor:
                await Actor.push_data([{'str': 'x' * 10000} for _ in range(5000)])  # ~50MB

        actor = await make_actor('push-data-over-9mb', main_func=main)

        run_result = await actor.call()

        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'
        async for item in actor.last_run().dataset().iterate_items():
            assert item['str'] == 'x' * 10000


class TestActorOpenDataset:
    async def test_same_references_default(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            async with Actor:
                dataset1 = await Actor.open_dataset()
                dataset2 = await Actor.open_dataset()
                assert dataset1 is dataset2

        actor = await make_actor('dataset-same-ref-default', main_func=main)

        run_result = await actor.call()
        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'

    async def test_same_references_named(self, make_actor: ActorFactory) -> None:
        dataset_name = generate_unique_resource_name('dataset')

        async def main() -> None:
            async with Actor:
                input_object = await Actor.get_input()
                dataset_name = input_object['datasetName']
                dataset_by_name_1 = await Actor.open_dataset(name=dataset_name)
                dataset_by_name_2 = await Actor.open_dataset(name=dataset_name)
                assert dataset_by_name_1 is dataset_by_name_2

                dataset_by_id_1 = await Actor.open_dataset(id=dataset_by_name_1._id)
                dataset_by_id_2 = await Actor.open_dataset(id=dataset_by_name_1._id)
                assert dataset_by_id_1 is dataset_by_name_1
                assert dataset_by_id_2 is dataset_by_id_1

                await dataset_by_name_1.drop()

        actor = await make_actor('dataset-same-ref-named', main_func=main)

        run_result = await actor.call(run_input={'datasetName': dataset_name})
        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'

    async def test_force_cloud(self, apify_client_async: ApifyClientAsync, monkeypatch: pytest.MonkeyPatch) -> None:
        assert apify_client_async.token is not None
        monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_client_async.token)

        dataset_name = generate_unique_resource_name('dataset')
        dataset_item = {'foo': 'bar'}

        async with Actor:
            dataset = await Actor.open_dataset(name=dataset_name, force_cloud=True)
            dataset_id = dataset._id

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
