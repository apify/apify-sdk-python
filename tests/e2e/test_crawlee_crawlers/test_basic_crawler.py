from __future__ import annotations

from typing import TYPE_CHECKING

from .conftest import _read_actor_source, _verify_crawler_results

if TYPE_CHECKING:
    from ..conftest import MakeActorFunction, RunActorFunction


async def test_basic_crawler(make_actor: MakeActorFunction, run_actor: RunActorFunction) -> None:
    actor = await make_actor(
        label='crawl-basic',
        source_files={
            'server.py': _read_actor_source('server.py'),
            'src/main.py': _read_actor_source('main_basic_crawler.py'),
        },
    )
    run_result = await run_actor(actor)
    await _verify_crawler_results(actor, run_result, 'BasicCrawler')
