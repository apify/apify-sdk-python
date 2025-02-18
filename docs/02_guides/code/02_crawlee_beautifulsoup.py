from __future__ import annotations

from crawlee.crawlers import BeautifulSoupCrawler, BeautifulSoupCrawlingContext

from apify import Actor


async def main() -> None:
    # Enter the context of the Actor.
    async with Actor:
        # Retrieve the Actor input, and use default values if not provided.
        actor_input = await Actor.get_input() or {}
        start_urls = [
            url.get('url')
            for url in actor_input.get(
                'start_urls',
                [{'url': 'https://apify.com'}],
            )
        ]

        # Exit if no start URLs are provided.
        if not start_urls:
            Actor.log.info('No start URLs specified in Actor input, exiting...')
            await Actor.exit()

        # Create a crawler.
        crawler = BeautifulSoupCrawler(
            # Limit the crawl to max requests.
            # Remove or increase it for crawling all links.
            max_requests_per_crawl=50,
        )

        # Define a request handler, which will be called for every request.
        @crawler.router.default_handler
        async def request_handler(context: BeautifulSoupCrawlingContext) -> None:
            url = context.request.url
            Actor.log.info(f'Scraping {url}...')

            # Extract the desired data.
            data = {
                'url': context.request.url,
                'title': context.soup.title.string if context.soup.title else None,
                'h1s': [h1.text for h1 in context.soup.find_all('h1')],
                'h2s': [h2.text for h2 in context.soup.find_all('h2')],
                'h3s': [h3.text for h3 in context.soup.find_all('h3')],
            }

            # Store the extracted data to the default dataset.
            await context.push_data(data)

            # Enqueue additional links found on the current page.
            await context.enqueue_links()

        # Run the crawler with the starting requests.
        await crawler.run(start_urls)
