from __future__ import annotations

from typing import TYPE_CHECKING

from .conftest import _TEST_SERVER_PY, _verify_crawler_results

if TYPE_CHECKING:
    from ..conftest import MakeActorFunction, RunActorFunction

_BEAUTIFULSOUP_CRAWLER_MAIN_PY = """\
from __future__ import annotations

from crawlee.crawlers import BeautifulSoupCrawler, BeautifulSoupCrawlingContext

from apify import Actor


async def main() -> None:
    async with Actor:
        pages_visited: list[str] = []
        crawler = BeautifulSoupCrawler()

        @crawler.router.default_handler
        async def handler(context: BeautifulSoupCrawlingContext) -> None:
            pages_visited.append(context.request.url)
            await context.enqueue_links()

            if '/products/' in context.request.url:
                name_tag = context.soup.find('h1')
                price_tag = context.soup.find('span', class_='price')
                desc_tag = context.soup.find('p', class_='description')
                if name_tag:
                    await context.push_data({
                        'url': context.request.url,
                        'name': name_tag.get_text(strip=True),
                        'price': price_tag.get_text(strip=True) if price_tag else '',
                        'description': desc_tag.get_text(strip=True) if desc_tag else '',
                    })

        await crawler.run(['http://localhost:8080/'])

        await Actor.set_value('CRAWLER_RESULT', {
            'pages_visited_count': len(pages_visited),
            'crawler_type': 'BeautifulSoupCrawler',
        })
"""


async def test_beautifulsoup_crawler(make_actor: MakeActorFunction, run_actor: RunActorFunction) -> None:
    actor = await make_actor(
        label='crawl-bsoup',
        source_files={'server.py': _TEST_SERVER_PY, 'src/main.py': _BEAUTIFULSOUP_CRAWLER_MAIN_PY},
        additional_requirements=['crawlee[beautifulsoup]>=1.0.0,<2.0.0'],
    )
    run_result = await run_actor(actor)
    await _verify_crawler_results(actor, run_result, 'BeautifulSoupCrawler')
