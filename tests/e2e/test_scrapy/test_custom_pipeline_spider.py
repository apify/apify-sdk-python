from __future__ import annotations

from typing import TYPE_CHECKING

from .conftest import get_scrapy_source_files, read_actor_source, verify_spider_results

if TYPE_CHECKING:
    from ..conftest import MakeActorFunction, RunActorFunction

_EXPECTED_PRODUCTS = {
    'Widget A': {'price': '19.99', 'description': 'A basic widget for everyday use'},
    'Widget B': {'price': '29.99', 'description': 'An advanced widget with extra features'},
    'Widget C': {'price': '39.99', 'description': 'A premium widget for professionals'},
}


async def test_custom_pipeline_spider(make_actor: MakeActorFunction, run_actor: RunActorFunction) -> None:
    actor = await make_actor(
        label='scrapy-pipeline',
        source_files=get_scrapy_source_files(
            'spider_custom_pipeline.py',
            'CustomPipelineSpider',
            extra_source_files={
                'src/main.py': read_actor_source('main_custom_pipeline.py'),
                'src/settings_custom_pipeline.py': read_actor_source('settings_custom_pipeline.py'),
                'src/pipelines.py': read_actor_source('pipelines.py'),
            },
        ),
        additional_requirements=['scrapy~=2.12.0'],
    )
    run_result = await run_actor(actor)
    await verify_spider_results(actor, run_result, expected_products=_EXPECTED_PRODUCTS)
