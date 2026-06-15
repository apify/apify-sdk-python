import asyncio

from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext
from crawlee.router import Router

from apify import Actor

# Define the router up front. The crawler is created later in `main`.
router = Router[PlaywrightCrawlingContext]()


# Handler called for every request.
@router.default_handler
async def request_handler(context: PlaywrightCrawlingContext) -> None:
    Actor.log.info(f'Scraping {context.request.url} ...')

    data = {
        'url': context.request.url,
        'title': await context.page.title(),
        'h1s': [await h1.text_content() for h1 in await context.page.locator('h1').all()],
        'h2s': [await h2.text_content() for h2 in await context.page.locator('h2').all()],
        'h3s': [await h3.text_content() for h3 in await context.page.locator('h3').all()],
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

        # Common Chrome flags for running the browser in a container.
        browser_args = ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']

        crawler = PlaywrightCrawler(
            proxy_configuration=proxy_configuration,
            request_handler=router,
            # Cap the crawl. Remove or increase the limit to follow all links.
            max_requests_per_crawl=50,
            headless=True,
            browser_launch_options={'args': browser_args},
        )

        await crawler.run(start_urls)


if __name__ == '__main__':
    asyncio.run(main())
