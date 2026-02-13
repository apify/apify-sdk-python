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
                    await context.push_data(
                        {
                            'url': context.request.url,
                            'name': name,
                            'price': price,
                            'description': description,
                        }
                    )

        await crawler.run(['http://localhost:8080/'])

        await Actor.set_value(
            'CRAWLER_RESULT',
            {
                'pages_visited_count': len(pages_visited),
                'crawler_type': 'AdaptivePlaywrightCrawler',
            },
        )
