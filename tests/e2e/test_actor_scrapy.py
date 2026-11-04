from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .._utils import poll_until_condition

if TYPE_CHECKING:
    from .conftest import MakeActorFunction, RunActorFunction


async def test_actor_scrapy_title_spider(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    base_path = Path('docs/03_guides/code/scrapy_project')

    actor_source_files = {
        'src/__init__.py': (base_path / 'src/__init__.py').read_text(),
        'src/__main__.py': (base_path / 'src/__main__.py').read_text(),
        'src/items.py': (base_path / 'src/items.py').read_text(),
        'src/main.py': (base_path / 'src/main.py').read_text(),
        'src/settings.py': (base_path / 'src/settings.py').read_text(),
        'src/spiders/__init__.py': (base_path / 'src/spiders/__init__.py').read_text(),
        'src/spiders/title.py': (base_path / 'src/spiders/title.py').read_text(),
    }

    actor = await make_actor(
        'actor-scrapy-title-spider',
        source_files=actor_source_files,
        additional_requirements=['scrapy>=2.14.0'],
    )
    run_result = await run_actor(
        actor,
        run_input={
            'startUrls': [{'url': 'https://crawlee.dev'}],
            'allowedDomains': ['crawlee.dev'],
            'proxyConfiguration': {'useApifyProxy': True},
        },
        force_permission_level='FULL_PERMISSIONS',
    )

    assert run_result.status == 'SUCCEEDED'

    items = await poll_until_condition(
        actor.last_run().dataset().list_items,
        lambda page: len(page.items) > 1 and len(page.items) >= page.total,
        timeout=30,
    )

    # The start page and the pages it links to (`DEPTH_LIMIT` is 1, `CLOSESPIDER_PAGECOUNT` is 10), each scraped once.
    urls = [item['url'] for item in items.items]
    assert 'https://crawlee.dev' in urls
    assert len(urls) > 1
    assert len(urls) == len(set(urls)), urls

    for item in items.items:
        assert 'url' in item
        assert 'title' in item
