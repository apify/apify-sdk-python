from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

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
        additional_requirements=['scrapy~=2.12.0'],
    )
    run_result = await run_actor(
        actor,
        run_input={
            'startUrls': [{'url': 'https://crawlee.dev'}],
            'allowedDomains': ['crawlee.dev'],
            'proxyConfiguration': {'useApifyProxy': True},
        },
    )

    assert run_result.status == 'SUCCEEDED'

    items = await actor.last_run().dataset().list_items()

    # CLOSESPIDER_PAGECOUNT is set to 10 in the spider settings.
    assert items.count >= 9

    for item in items.items:
        assert 'url' in item
        assert 'title' in item
