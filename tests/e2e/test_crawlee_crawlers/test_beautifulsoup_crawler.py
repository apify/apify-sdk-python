from __future__ import annotations

from typing import TYPE_CHECKING

from .conftest import _read_actor_source, _verify_crawler_results

if TYPE_CHECKING:
    from ..conftest import MakeActorFunction, RunActorFunction


async def test_beautifulsoup_crawler(make_actor: MakeActorFunction, run_actor: RunActorFunction) -> None:
    actor = await make_actor(
        label='crawl-bsoup',
        source_files={
            'server.py': _read_actor_source('server.py'),
            'src/main.py': _read_actor_source('main_beautifulsoup_crawler.py'),
        },
        additional_requirements=['crawlee[beautifulsoup]>=1.0.0,<2.0.0'],
    )
    run_result = await run_actor(actor)
    await _verify_crawler_results(actor, run_result, 'BeautifulSoupCrawler')
