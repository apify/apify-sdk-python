from __future__ import annotations

from typing import TYPE_CHECKING

from .conftest import get_scrapy_source_files, verify_spider_results

if TYPE_CHECKING:
    from ..conftest import MakeActorFunction, RunActorFunction


async def test_itemloader_spider(make_actor: MakeActorFunction, run_actor: RunActorFunction) -> None:
    actor = await make_actor(
        label='scrapy-itemloader',
        source_files=get_scrapy_source_files('spider_itemloader.py', 'ItemLoaderSpider'),
        additional_requirements=['scrapy>=2.14.0'],
    )
    run_result = await run_actor(actor)
    await verify_spider_results(actor, run_result)
