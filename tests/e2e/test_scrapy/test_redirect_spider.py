from __future__ import annotations

from typing import TYPE_CHECKING

from ..._utils import poll_until_condition
from .conftest import get_scrapy_source_files

if TYPE_CHECKING:
    from ..conftest import MakeActorFunction, RunActorFunction


async def test_redirect_spider(make_actor: MakeActorFunction, run_actor: RunActorFunction) -> None:
    """A redirect is followed instead of being deduplicated against the request it was redirected from."""
    actor = await make_actor(
        label='scrapy-redirect',
        source_files=get_scrapy_source_files('spider_redirect.py', 'RedirectSpider'),
        additional_requirements=['scrapy>=2.14.0'],
    )
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'

    items = await poll_until_condition(
        actor.last_run().dataset().list_items,
        lambda page: len(page.items) >= 1,
        timeout=30,
    )
    assert items.items == [{'url': 'http://localhost:8080/redirect-target', 'title': 'Redirect Target'}]
