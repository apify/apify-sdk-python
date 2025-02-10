from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .conftest import MakeActorFunction, RunActorFunction

from ._utils import read_file


async def test_actor_scrapy_title_spider(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    actor_source_files = {
        'src/spiders.py': read_file('docs/02_guides/code/scrapy_project/src/spiders.py'),
        'src/items.py': read_file('docs/02_guides/code/scrapy_project/src/items.py'),
        'src/settings.py': read_file('docs/02_guides/code/scrapy_project/src/settings.py'),
        'src/__init__.py': read_file('docs/02_guides/code/scrapy_project/src/__init__.py'),
        'src/main.py': read_file('docs/02_guides/code/scrapy_project/src/main.py'),
        'src/__main__.py': read_file('docs/02_guides/code/scrapy_project/src/__main__.py'),
    }

    actor = await make_actor('actor-scrapy-title-spider', source_files=actor_source_files)
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

    assert items.count >= 10

    for item in items.items:
        assert 'url' in item
        assert 'title' in item
