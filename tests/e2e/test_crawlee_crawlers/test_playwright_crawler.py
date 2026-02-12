from __future__ import annotations

from typing import TYPE_CHECKING

from .conftest import _PLAYWRIGHT_DOCKERFILE, _TEST_SERVER_PY, _verify_crawler_results

if TYPE_CHECKING:
    from ..conftest import MakeActorFunction, RunActorFunction

_PLAYWRIGHT_CRAWLER_MAIN_PY = """\
from __future__ import annotations

from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext

from apify import Actor


async def main() -> None:
    async with Actor:
        pages_visited: list[str] = []
        crawler = PlaywrightCrawler()

        @crawler.router.default_handler
        async def handler(context: PlaywrightCrawlingContext) -> None:
            pages_visited.append(context.request.url)
            await context.enqueue_links()

            if '/products/' in context.request.url:
                name = await context.page.locator('h1').text_content()
                price = await context.page.locator('span.price').text_content()
                description = await context.page.locator('p.description').text_content()
                if name:
                    await context.push_data({
                        'url': context.request.url,
                        'name': name.strip(),
                        'price': (price or '').strip(),
                        'description': (description or '').strip(),
                    })

        await crawler.run(['http://localhost:8080/'])

        await Actor.set_value('CRAWLER_RESULT', {
            'pages_visited_count': len(pages_visited),
            'crawler_type': 'PlaywrightCrawler',
        })
"""


async def test_playwright_crawler(make_actor: MakeActorFunction, run_actor: RunActorFunction) -> None:
    actor = await make_actor(
        label='crawl-playwright',
        source_files={
            'server.py': _TEST_SERVER_PY,
            'src/main.py': _PLAYWRIGHT_CRAWLER_MAIN_PY,
            'Dockerfile': _PLAYWRIGHT_DOCKERFILE,
        },
        additional_requirements=['crawlee[playwright]>=1.0.0,<2.0.0'],
        memory_mbytes=1024,
    )
    run_result = await run_actor(actor)
    await _verify_crawler_results(actor, run_result, 'PlaywrightCrawler')
