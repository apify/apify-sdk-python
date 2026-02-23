from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apify_client._resource_clients import ActorClientAsync

    from apify._models import ActorRun

_PYTHON_VERSION = f'{sys.version_info[0]}.{sys.version_info[1]}'

_ACTOR_SOURCE_DIR = Path(__file__).parent / 'actor_source'


def read_actor_source(filename: str) -> str:
    return (_ACTOR_SOURCE_DIR / filename).read_text()


def get_playwright_dockerfile() -> str:
    return read_actor_source('playwright.Dockerfile').replace(
        'PYTHON_VERSION_PLACEHOLDER',
        _PYTHON_VERSION,
    )


_EXPECTED_PRODUCTS = {
    'Widget A': {'price': '$19.99', 'description': 'A basic widget for everyday use'},
    'Widget B': {'price': '$29.99', 'description': 'An advanced widget with extra features'},
    'Widget C': {'price': '$39.99', 'description': 'A premium widget for professionals'},
}


async def verify_crawler_results(
    actor: ActorClientAsync,
    run_result: ActorRun,
    expected_crawler_type: str,
) -> None:
    """Verify dataset items and KVS record after a crawler Actor run."""
    assert run_result.status == 'SUCCEEDED'

    # Verify dataset items.
    items = await actor.last_run().dataset().list_items()
    assert items.count == 3

    items_by_name = {item['name']: item for item in items.items}

    for name, expected in _EXPECTED_PRODUCTS.items():
        assert name in items_by_name, f'Missing product: {name}'
        item = items_by_name[name]
        assert 'url' in item
        assert item['price'] == expected['price']
        assert item['description'] == expected['description']

    # Verify KVS record.
    kvs_record = await actor.last_run().key_value_store().get_record('CRAWLER_RESULT')
    assert kvs_record is not None
    result = kvs_record['value']
    assert result['crawler_type'] == expected_crawler_type
    # With max_crawl_depth=2, the server has 9 pages reachable (homepage, 2 categories, about, /deep/1,
    # 3 products, /deep/2). The crawler should visit most of them but not go beyond /deep/2.
    assert result['pages_visited_count'] >= 5
    assert result['pages_visited_count'] <= 15
