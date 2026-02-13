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
                    await context.push_data(
                        {
                            'url': context.request.url,
                            'name': name.strip(),
                            'price': (price or '').strip(),
                            'description': (description or '').strip(),
                        }
                    )

        await crawler.run(['http://localhost:8080/'])

        await Actor.set_value(
            'CRAWLER_RESULT',
            {
                'pages_visited_count': len(pages_visited),
                'crawler_type': 'PlaywrightCrawler',
            },
        )
