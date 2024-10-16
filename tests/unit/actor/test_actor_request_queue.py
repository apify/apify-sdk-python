from __future__ import annotations

import pytest

from apify import Actor

# NOTE: We only test the references here. Actual tests for the implementations are in storages/


async def test_open_throws_without_init() -> None:
    with pytest.raises(RuntimeError):
        await Actor.open_request_queue()


async def test_open_returns_same_references() -> None:
    async with Actor:
        rq1 = await Actor.open_request_queue()
        rq2 = await Actor.open_request_queue()
        assert rq1 is rq2

        rq_name = 'non-default'
        rq_by_name_1 = await Actor.open_key_value_store(name=rq_name)
        rq_by_name_2 = await Actor.open_key_value_store(name=rq_name)
        assert rq_by_name_1 is rq_by_name_2

        rq_by_id_1 = await Actor.open_key_value_store(id=rq_by_name_1._id)
        rq_by_id_2 = await Actor.open_key_value_store(id=rq_by_name_1._id)
        assert rq_by_id_1 is rq_by_name_1
        assert rq_by_id_2 is rq_by_id_1
