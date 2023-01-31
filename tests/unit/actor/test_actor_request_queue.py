import pytest

from apify import Actor

# NOTE: We only test the references here. Actual tests for the implementations are in storages/


class TestActorOpenRequestQueue:

    async def test_throws_without_init(self) -> None:
        with pytest.raises(RuntimeError):
            await Actor.open_request_queue()

    async def test_same_references(self) -> None:
        async with Actor:
            rq1 = await Actor.open_request_queue()
            rq2 = await Actor.open_request_queue()
            assert rq1 is rq2
            rq_name = 'non-default'
            rq_named1 = await Actor.open_request_queue(rq_name)
            rq_named2 = await Actor.open_request_queue(rq_name)
            assert rq_named1 is rq_named2
