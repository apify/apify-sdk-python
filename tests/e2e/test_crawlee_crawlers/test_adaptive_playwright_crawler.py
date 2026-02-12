from __future__ import annotations

from typing import TYPE_CHECKING

from .conftest import _PLAYWRIGHT_DOCKERFILE, _TEST_SERVER_PY, _verify_crawler_results

if TYPE_CHECKING:
    from ..conftest import MakeActorFunction, RunActorFunction

_ADAPTIVE_PLAYWRIGHT_CRAWLER_MAIN_PY = """\
from __future__ import annotations

from crawlee.crawlers import AdaptivePlaywrightCrawler, AdaptivePlaywrightCrawlingContext

from apify import Actor


async def main() -> None:
    async with Actor:
        pages_visited: list[str] = []
        crawler = AdaptivePlaywrightCrawler.with_parsel_static_parser()

        @crawler.router.default_handler
        async def handler(context: AdaptivePlaywrightCrawlingContext) -> None:
            pages_visited.append(context.request.url)
            await context.enqueue_links()

            if '/products/' in context.request.url:
                name = context.parsed_content.css('h1::text').get('').strip()
                price = context.parsed_content.css('span.price::text').get('').strip()
                description = context.parsed_content.css('p.description::text').get('').strip()
                if name:
                    await context.push_data({
                        'url': context.request.url,
                        'name': name,
                        'price': price,
                        'description': description,
                    })

        await crawler.run(['http://localhost:8080/'])

        await Actor.set_value('CRAWLER_RESULT', {
            'pages_visited_count': len(pages_visited),
            'crawler_type': 'AdaptivePlaywrightCrawler',
        })
"""


async def test_adaptive_playwright_crawler(make_actor: MakeActorFunction, run_actor: RunActorFunction) -> None:
    actor = await make_actor(
        label='crawl-adaptive',
        source_files={
            'server.py': _TEST_SERVER_PY,
            'src/main.py': _ADAPTIVE_PLAYWRIGHT_CRAWLER_MAIN_PY,
            'Dockerfile': _PLAYWRIGHT_DOCKERFILE,
        },
        additional_requirements=['crawlee[all]>=1.0.0,<2.0.0'],
    )
    run_result = await run_actor(actor)
    await _verify_crawler_results(actor, run_result, 'AdaptivePlaywrightCrawler')
