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
                    await context.push_data(
                        {
                            'url': context.request.url,
                            'name': name_tag.get_text(strip=True),
                            'price': price_tag.get_text(strip=True) if price_tag else '',
                            'description': desc_tag.get_text(strip=True) if desc_tag else '',
                        }
                    )

        await crawler.run(['http://localhost:8080/'])

        await Actor.set_value(
            'CRAWLER_RESULT',
            {
                'pages_visited_count': len(pages_visited),
                'crawler_type': 'BeautifulSoupCrawler',
            },
        )
