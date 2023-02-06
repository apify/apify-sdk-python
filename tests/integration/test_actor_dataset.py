
from apify import Actor

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
        list_page = await actor.last_run().dataset().list_items(limit=desired_item_count)
        assert list_page.items[0]['id'] == 0
        assert list_page.items[-1]['id'] == desired_item_count - 1


class TestActorOpenDataset:
    async def test_same_references(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            async with Actor:
                dataset1 = await Actor.open_dataset()
                dataset2 = await Actor.open_dataset()
                assert dataset1 is dataset2

        actor = await make_actor('dataset-same-references', main_func=main)

        run_result = await actor.call()
        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'
