from __future__ import annotations

from typing import TYPE_CHECKING

from .conftest import read_actor_source, verify_crawler_results

if TYPE_CHECKING:
    from ..conftest import MakeActorFunction, RunActorFunction


async def test_playwright_crawler(make_actor: MakeActorFunction, run_actor: RunActorFunction) -> None:
    actor = await make_actor(
        label='crawl-playwright',
        source_files={
            'actor/main.py': read_actor_source('main_playwright_crawler.py'),
            'Dockerfile': read_actor_source('playwright.Dockerfile'),
        },
        additional_requirements=['crawlee[playwright]'],
        memory_mbytes=1024,
    )
    run_result = await run_actor(actor)
    await verify_crawler_results(actor, run_result, 'PlaywrightCrawler')
