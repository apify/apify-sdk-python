from __future__ import annotations

from typing import TYPE_CHECKING

from .conftest import _get_playwright_dockerfile, _read_actor_source, _verify_crawler_results

if TYPE_CHECKING:
    from ..conftest import MakeActorFunction, RunActorFunction


async def test_playwright_crawler(make_actor: MakeActorFunction, run_actor: RunActorFunction) -> None:
    actor = await make_actor(
        label='crawl-playwright',
        source_files={
            'server.py': _read_actor_source('server.py'),
            'src/main.py': _read_actor_source('main_playwright_crawler.py'),
            'Dockerfile': _get_playwright_dockerfile(),
        },
        additional_requirements=['crawlee[playwright]>=1.0.0,<2.0.0'],
        memory_mbytes=1024,
    )
    run_result = await run_actor(actor)
    await _verify_crawler_results(actor, run_result, 'PlaywrightCrawler')
