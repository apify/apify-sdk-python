from __future__ import annotations

from html.parser import HTMLParser
from typing import TYPE_CHECKING

from crawlee.crawlers import BasicCrawler

from apify import Actor

if TYPE_CHECKING:
    from crawlee._types import BasicCrawlingContext


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.data: dict[str, str] = {}
        self._in_tag: str | None = None
        self._in_class: str = ''

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == 'a' and (href := attrs_dict.get('href')):
            self.links.append(href)
        self._in_tag = tag
        self._in_class = attrs_dict.get('class', '') or ''

    def handle_endtag(self, tag: str) -> None:  # noqa: ARG002
        self._in_tag = None
        self._in_class = ''

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self._in_tag == 'h1':
            self.data['name'] = text
        elif self._in_tag == 'span' and self._in_class == 'price':
            self.data['price'] = text
        elif self._in_tag == 'p' and self._in_class == 'description':
            self.data['description'] = text


async def main() -> None:
    async with Actor:
        pages_visited: list[str] = []
        crawler = BasicCrawler(max_crawl_depth=2)

        @crawler.router.default_handler
        async def handler(context: BasicCrawlingContext) -> None:
            pages_visited.append(context.request.url)

            response = await context.send_request(context.request.url)
            html = (await response.read()).decode()

            parser = _PageParser()
            parser.feed(html)

            base_url = 'http://localhost:8080'
            await context.add_requests([f'{base_url}{link}' for link in parser.links if link.startswith('/')])

            if '/products/' in context.request.url and parser.data.get('name'):
                await context.push_data({'url': context.request.url, **parser.data})

        await crawler.run(['http://localhost:8080/'])

        await Actor.set_value(
            'CRAWLER_RESULT',
            {
                'pages_visited_count': len(pages_visited),
                'crawler_type': 'BasicCrawler',
            },
        )
