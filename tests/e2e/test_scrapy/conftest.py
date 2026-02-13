from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apify_client.clients.resource_clients import ActorClientAsync

    from apify._models import ActorRun

_ACTOR_SOURCE_DIR = Path(__file__).parent / 'actor_source'


def read_actor_source(filename: str) -> str:
    return (_ACTOR_SOURCE_DIR / filename).read_text()


def get_scrapy_source_files(
    spider_file: str,
    spider_class_name: str,
    *,
    extra_source_files: dict[str, str] | None = None,
) -> dict[str, str]:
    source_files: dict[str, str] = {
        'src/__main__.py': read_actor_source('__main__.py'),
        'src/main.py': read_actor_source('main.py'),
        'src/settings.py': read_actor_source('settings.py'),
        'src/items.py': read_actor_source('items.py'),
        'src/spiders/__init__.py': f'from .spider import {spider_class_name} as Spider\n',
        'src/spiders/spider.py': read_actor_source(spider_file),
    }
    if extra_source_files:
        source_files.update(extra_source_files)
    return source_files


_EXPECTED_PRODUCTS = {
    'Widget A': {'price': '$19.99', 'description': 'A basic widget for everyday use'},
    'Widget B': {'price': '$29.99', 'description': 'An advanced widget with extra features'},
    'Widget C': {'price': '$39.99', 'description': 'A premium widget for professionals'},
}


async def verify_spider_results(
    actor: ActorClientAsync,
    run_result: ActorRun,
    *,
    expected_products: dict[str, dict[str, str]] | None = None,
) -> None:
    assert run_result.status == 'SUCCEEDED'

    products = expected_products or _EXPECTED_PRODUCTS

    items = await actor.last_run().dataset().list_items()
    assert items.count == 3

    items_by_name = {item['name']: item for item in items.items}

    for name, expected in products.items():
        assert name in items_by_name, f'Missing product: {name}'
        item = items_by_name[name]
        assert 'url' in item
        for key, value in expected.items():
            assert item[key] == value, f'Product {name}: expected {key}={value!r}, got {item[key]!r}'
