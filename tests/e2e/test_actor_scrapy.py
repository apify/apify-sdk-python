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
    docs_package_path = Path('docs/03_guides/code/scrapy_project/src')
    file_names = (
        '__init__.py',
        '__main__.py',
        'items.py',
        'main.py',
        'settings.py',
        'spiders/__init__.py',
        'spiders/title.py',
    )

    # The guide's project is the `src` package of the Apify Scrapy template, while test Actors run the `actor` package.
    actor_source_files = {
        f'actor/{file_name}': (docs_package_path / file_name).read_text().replace("'src.", "'actor.")
        for file_name in file_names
    }

    actor = await make_actor(
        'actor-scrapy-title-spider',
        source_files=actor_source_files,
        additional_requirements=['scrapy>=2.14.0'],
    )
    run_result = await run_actor(
        actor,
        run_input={
            'startUrls': [{'url': 'https://crawlee.dev/'}],
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
    assert 'https://crawlee.dev/' in urls
    assert len(urls) > 1
    assert len(urls) == len(set(urls)), urls

    for item in items.items:
        assert 'url' in item
        assert 'title' in item
