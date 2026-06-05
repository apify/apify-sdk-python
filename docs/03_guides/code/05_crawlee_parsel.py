import asyncio

from crawlee.crawlers import ParselCrawler, ParselCrawlingContext
from crawlee.router import Router

from apify import Actor

# Define the router up front; the crawler is created later in `main`.
router = Router[ParselCrawlingContext]()


# Handler called for every request.
@router.default_handler
async def request_handler(context: ParselCrawlingContext) -> None:
    Actor.log.info(f'Scraping {context.request.url} ...')

    data = {
        'url': context.request.url,
        'title': context.selector.xpath('//title/text()').get(),
        'h1s': context.selector.xpath('//h1/text()').getall(),
        'h2s': context.selector.xpath('//h2/text()').getall(),
        'h3s': context.selector.xpath('//h3/text()').getall(),
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

        crawler = ParselCrawler(
            proxy_configuration=proxy_configuration,
            request_handler=router,
            # Cap the crawl; remove or increase to follow all links.
            max_requests_per_crawl=50,
        )

        await crawler.run(start_urls)


if __name__ == '__main__':
    asyncio.run(main())
