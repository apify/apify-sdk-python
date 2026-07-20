import asyncio

from crawlee.crawlers import BeautifulSoupCrawler, BeautifulSoupCrawlingContext
from crawlee.router import Router

from apify import Actor

# Define the router up front. The crawler is created later in `main`.
router = Router[BeautifulSoupCrawlingContext]()


# Handler called for every request.
@router.default_handler
async def request_handler(context: BeautifulSoupCrawlingContext) -> None:
    Actor.log.info(f'Scraping {context.request.url} ...')

    data = {
        'url': context.request.url,
        'title': context.soup.title.string if context.soup.title else None,
        'h1s': [h1.text for h1 in context.soup.find_all('h1')],
        'h2s': [h2.text for h2 in context.soup.find_all('h2')],
        'h3s': [h3.text for h3 in context.soup.find_all('h3')],
    }

    await context.push_data(data)
    Actor.log.info(f'Stored data from {context.request.url} (title={data["title"]!r}).')

    # Enqueue links found on the page.
    await context.enqueue_links(strategy='same-domain')


async def main() -> None:
    async with Actor:
        # Read the Actor input.
        actor_input = await Actor.get_input() or {}
        start_urls = [
            url.get('url')
            for url in actor_input.get('startUrls', [{'url': 'https://crawlee.dev'}])
        ]

        if not start_urls:
            Actor.log.info('No start URLs specified in Actor input, exiting...')
            await Actor.exit()

        # Crawlee rotates the proxy URL per request on its own.
        proxy_configuration = await Actor.create_proxy_configuration()
        if proxy_configuration is None:
            raise RuntimeError('Failed to create the proxy configuration.')

        crawler = BeautifulSoupCrawler(
            proxy_configuration=proxy_configuration,
            request_handler=router,
            # Cap the crawl. Remove or increase the limit to follow all links.
            max_requests_per_crawl=10,
        )

        await crawler.run(start_urls)


if __name__ == '__main__':
    asyncio.run(main())
