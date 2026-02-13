from __future__ import annotations

import re

from crawlee.crawlers import HttpCrawler, HttpCrawlingContext

from apify import Actor


async def main() -> None:
    async with Actor:
        pages_visited: list[str] = []
        crawler = HttpCrawler(max_crawl_depth=2)

        @crawler.router.default_handler
        async def handler(context: HttpCrawlingContext) -> None:
            pages_visited.append(context.request.url)
            html = (await context.http_response.read()).decode()

            links = re.findall(r'href="(/[^"]*)"', html)
            base_url = 'http://localhost:8080'
            await context.add_requests([f'{base_url}{link}' for link in links])

            if '/products/' in context.request.url:
                name_match = re.search(r'<h1>(.*?)</h1>', html)
                price_match = re.search(r'<span class="price">(.*?)</span>', html)
                desc_match = re.search(r'<p class="description">(.*?)</p>', html)
                if name_match:
                    await context.push_data(
                        {
                            'url': context.request.url,
                            'name': name_match.group(1),
                            'price': price_match.group(1) if price_match else '',
                            'description': desc_match.group(1) if desc_match else '',
                        }
                    )

        await crawler.run(['http://localhost:8080/'])

        await Actor.set_value(
            'CRAWLER_RESULT',
            {
                'pages_visited_count': len(pages_visited),
                'crawler_type': 'HttpCrawler',
            },
        )
