import pytest

from apify import Actor
from apify.consts import ApifyEnvVars
from apify_client import ApifyClientAsync

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
                rq_by_name_1 = await Actor.open_request_queue(name=rq_name)
                rq_by_name_2 = await Actor.open_request_queue(name=rq_name)
                assert rq_by_name_1 is rq_by_name_2

                rq_by_id_1 = await Actor.open_request_queue(id=rq_by_name_1._id)
                rq_by_id_2 = await Actor.open_request_queue(id=rq_by_name_1._id)
                assert rq_by_id_1 is rq_by_name_1
                assert rq_by_id_2 is rq_by_id_1

                await rq_by_name_1.drop()

        actor = await make_actor('rq-same-ref-named', main_func=main)

        run_result = await actor.call(run_input={'rqName': rq_name})
        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'

    async def test_force_cloud(self, apify_client_async: ApifyClientAsync, monkeypatch: pytest.MonkeyPatch) -> None:
        assert apify_client_async.token is not None
        monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_client_async.token)

        request_queue_name = generate_unique_resource_name('request_queue')

        async with Actor:
            request_queue = await Actor.open_request_queue(name=request_queue_name, force_cloud=True)
            request_queue_id = request_queue._id

            request_info = await request_queue.add_request({'url': 'http://example.com'})

        request_queue_client = apify_client_async.request_queue(request_queue_id)

        try:
            request_queue_details = await request_queue_client.get()
            assert request_queue_details is not None
            assert request_queue_details.get('name') == request_queue_name

            request_queue_request = await request_queue_client.get_request(request_info['requestId'])
            assert request_queue_request is not None
            assert request_queue_request['url'] == 'http://example.com'
        finally:
            await request_queue_client.delete()
