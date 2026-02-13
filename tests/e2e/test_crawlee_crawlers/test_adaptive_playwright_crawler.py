from __future__ import annotations

from typing import TYPE_CHECKING

from .conftest import get_playwright_dockerfile, read_actor_source, verify_crawler_results

if TYPE_CHECKING:
    from ..conftest import MakeActorFunction, RunActorFunction


async def test_adaptive_playwright_crawler(make_actor: MakeActorFunction, run_actor: RunActorFunction) -> None:
    actor = await make_actor(
        label='crawl-adaptive',
        source_files={
            'server.py': read_actor_source('server.py'),
            'src/main.py': read_actor_source('main_adaptive_playwright_crawler.py'),
            'Dockerfile': get_playwright_dockerfile(),
        },
        additional_requirements=['crawlee[all]'],
        memory_mbytes=1024,
    )
    run_result = await run_actor(actor)
    await verify_crawler_results(actor, run_result, 'AdaptivePlaywrightCrawler')
