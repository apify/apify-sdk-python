from __future__ import annotations

from typing import TYPE_CHECKING

from .conftest import get_scrapy_source_files, verify_spider_results

if TYPE_CHECKING:
    from ..conftest import MakeActorFunction, RunActorFunction

_EXPECTED_PRODUCTS = {
    'Widget A': {
        'price': '$19.99',
        'description': 'A basic widget for everyday use',
        'source': 'E-commerce Test Store',
    },
    'Widget B': {
        'price': '$29.99',
        'description': 'An advanced widget with extra features',
        'source': 'E-commerce Test Store',
    },
    'Widget C': {
        'price': '$39.99',
        'description': 'A premium widget for professionals',
        'source': 'E-commerce Test Store',
    },
}


async def test_cb_kwargs_spider(make_actor: MakeActorFunction, run_actor: RunActorFunction) -> None:
    actor = await make_actor(
        label='scrapy-cb-kwargs',
        source_files=get_scrapy_source_files('spider_cb_kwargs.py', 'CbKwargsSpider'),
        additional_requirements=['scrapy>=2.14.0'],
    )
    run_result = await run_actor(actor)
    await verify_spider_results(actor, run_result, expected_products=_EXPECTED_PRODUCTS)
