from apify import Actor

from ._utils import generate_unique_resource_name
from .conftest import ActorFactory


class TestActorOpenRequestQueue:
    async def test_same_references_default(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            async with Actor:
                rq1 = await Actor.open_request_queue()
                rq2 = await Actor.open_request_queue()
                assert rq1 is rq2

        actor = await make_actor('rq-same-ref-default', main_func=main)

        run_result = await actor.call()
        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'

    async def test_same_references_named(self, make_actor: ActorFactory) -> None:
        rq_name = generate_unique_resource_name('request-queue')

        async def main() -> None:
            async with Actor:
                input_object = await Actor.get_input()
                rq_name = input_object['rqName']
                rq1 = await Actor.open_request_queue(rq_name)
                rq2 = await Actor.open_request_queue(rq_name)
                assert rq1 is rq2
                await rq1.drop()

        actor = await make_actor('rq-same-ref-named', main_func=main)

        run_result = await actor.call(run_input={'rqName': rq_name})
        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'
