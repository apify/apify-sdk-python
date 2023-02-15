from apify import Actor

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
        desired_item_count = 5000  # Also change inside main() if you're changing this

        async def main() -> None:
            desired_item_count = 5000
            async with Actor:
                await Actor.push_data([{'str': 'x' * 10000} for _ in range(desired_item_count)])  # ~50MB

        actor = await make_actor('push-data-over-9mb', main_func=main)

        run_result = await actor.call()

        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'
        list_page = await actor.last_run().dataset().list_items()
        assert list_page.items[0]['str'] == 'x' * 10000
        assert list_page.items[-1]['str'] == 'x' * 10000
        assert list_page.total == desired_item_count


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
                dataset1 = await Actor.open_dataset(name=dataset_name)
                dataset2 = await Actor.open_dataset(name=dataset_name)
                assert dataset1 is dataset2
                await dataset1.drop()

        actor = await make_actor('dataset-same-ref-named', main_func=main)

        run_result = await actor.call(run_input={'datasetName': dataset_name})
        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'
