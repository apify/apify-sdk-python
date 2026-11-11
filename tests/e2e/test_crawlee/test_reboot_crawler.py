from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from ..._utils import poll_until_condition
from .conftest import read_actor_source

if TYPE_CHECKING:
    from ..conftest import MakeActorFunction, RunActorFunction

# With `max_crawl_depth=2`, the crawler reaches the homepage, 2 categories, the about page, 3 products, `/deep/1`
# and `/deep/2`.
_EXPECTED_PAGE_COUNT = 9

_EXPECTED_PRODUCTS = {'Widget A', 'Widget B', 'Widget C'}


async def test_reboot_crawler(make_actor: MakeActorFunction, run_actor: RunActorFunction) -> None:
    """A crawl split by a reboot visits every page once and keeps its statistics from before the reboot."""
    actor = await make_actor(
        label='crawl-reboot',
        source_files={
            'actor/main.py': read_actor_source('main_reboot_crawler.py'),
        },
    )
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'
    assert run_result.stats.reboot_count == 1

    dataset = actor.last_run().dataset()
    items = await poll_until_condition(
        dataset.list_items,
        lambda page: len(page.items) >= len(_EXPECTED_PRODUCTS),
        timeout=30,
    )
    assert Counter(item['name'] for item in items.items) == Counter(_EXPECTED_PRODUCTS)

    result = await actor.last_run().key_value_store().get_record('CRAWLER_RESULT')
    assert result is not None
    assert result['value']['requests_finished'] == _EXPECTED_PAGE_COUNT
