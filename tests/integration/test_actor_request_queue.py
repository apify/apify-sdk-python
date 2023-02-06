from apify import Actor

from .conftest import ActorFactory


class TestActorOpenRequestQueue:
    async def test_same_references(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            async with Actor:
                rq1 = await Actor.open_request_queue()
                rq2 = await Actor.open_request_queue()
                assert rq1 is rq2

        actor = await make_actor('rq-same-references', main_func=main)

        run_result = await actor.call()
        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'
