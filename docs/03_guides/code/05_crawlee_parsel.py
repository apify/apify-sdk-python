import asyncio

from crawlee.crawlers import ParselCrawler, ParselCrawlingContext
from crawlee.router import Router

from apify import Actor

# Define the request router up front, so the crawler itself can be created later
# inside `main`, once the Apify Proxy configuration is available.
router = Router[ParselCrawlingContext]()


# Define a request handler, which will be called for every request.
@router.default_handler
async def request_handler(context: ParselCrawlingContext) -> None:
    Actor.log.info(f'Scraping {context.request.url} ...')

    # Extract the desired data.
    data = {
        'url': context.request.url,
        'title': context.selector.xpath('//title/text()').get(),
        'h1s': context.selector.xpath('//h1/text()').getall(),
        'h2s': context.selector.xpath('//h2/text()').getall(),
        'h3s': context.selector.xpath('//h3/text()').getall(),
    }

    # Store the extracted data to the default dataset.
    await context.push_data(data)
    Actor.log.info(f'Stored data from {context.request.url} (title={data["title"]!r}).')

    # Enqueue additional links found on the current page.
    await context.enqueue_links(strategy='same-domain')


async def main() -> None:
    # Enter the context of the Actor.
    async with Actor:
        # Retrieve the Actor input, and use default values if not provided.
        actor_input = await Actor.get_input() or {}
        start_urls = [
            url.get('url')
            for url in actor_input.get('startUrls', [{'url': 'https://crawlee.dev'}])
        ]

        # Exit if no start URLs are provided.
        if not start_urls:
            Actor.log.info('No start URLs specified in Actor input, exiting...')
            await Actor.exit()

        # Create a proxy configuration that routes requests through Apify Proxy.
        # Crawlee rotates the proxy URL for every request on its own.
        proxy_configuration = await Actor.create_proxy_configuration()
        if proxy_configuration is None:
            raise RuntimeError('Failed to create the proxy configuration.')

        # Create a crawler that uses the router above and routes requests through
        # Apify Proxy.
        crawler = ParselCrawler(
            proxy_configuration=proxy_configuration,
            request_handler=router,
            # Limit the crawl; remove or increase to follow all links.
            max_requests_per_crawl=50,
        )

        # Run the crawler with the starting requests.
        await crawler.run(start_urls)


if __name__ == '__main__':
    asyncio.run(main())
