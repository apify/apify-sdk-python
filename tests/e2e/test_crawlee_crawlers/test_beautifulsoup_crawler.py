from __future__ import annotations

from typing import TYPE_CHECKING

from .conftest import read_actor_source, verify_crawler_results

if TYPE_CHECKING:
    from ..conftest import MakeActorFunction, RunActorFunction


async def test_beautifulsoup_crawler(make_actor: MakeActorFunction, run_actor: RunActorFunction) -> None:
    actor = await make_actor(
        label='crawl-bsoup',
        source_files={
            'server.py': read_actor_source('server.py'),
            'src/main.py': read_actor_source('main_beautifulsoup_crawler.py'),
        },
        additional_requirements=['crawlee[beautifulsoup]'],
    )
    run_result = await run_actor(actor)
    await verify_crawler_results(actor, run_result, 'BeautifulSoupCrawler')
