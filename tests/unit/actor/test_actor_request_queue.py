from __future__ import annotations

import pytest

from apify import Actor


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

        rq_1_metadata = await rq_by_name_1.get_metadata()
        rq_by_id_1 = await Actor.open_key_value_store(id=rq_1_metadata.id)
        rq_by_id_2 = await Actor.open_key_value_store(id=rq_1_metadata.id)
        assert rq_by_id_1 is rq_by_name_1
        assert rq_by_id_2 is rq_by_id_1
