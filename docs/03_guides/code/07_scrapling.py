import asyncio
from typing import Any

from scrapling.fetchers import AsyncFetcher

from apify import Actor, Request


async def scrape_page(
    url: str,
    *,
    proxy_url: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Fetch a single page with Scrapling and extract its data and links.

    The page is fetched with Scrapling's asynchronous HTTP fetcher. The
    `impersonate` and `stealthy_headers` options make the request look like it
    comes from a real Chrome browser, which reduces the chance of being blocked.
    The returned response is also a Scrapling selector, so it can be queried with
    CSS selectors directly.
    """
    response = await AsyncFetcher.get(
        url,
        proxy=proxy_url,
        impersonate='chrome',
        stealthy_headers=True,
        timeout=60,
    )

    # Extract the desired data using CSS selectors. The `::text` pseudo-element
    # returns the text content of the matched elements.
    data = {
        'url': url,
        'title': response.css('title::text').get(),
        'h1s': response.css('h1::text').getall(),
        'h2s': response.css('h2::text').getall(),
        'h3s': response.css('h3::text').getall(),
    }

    # Collect absolute links from the page. The `::attr(href)` pseudo-selector
    # reads the attribute and `response.urljoin` resolves it against the page URL.
    links: list[str] = []
    for href in response.css('a::attr(href)').getall():
        link_url = response.urljoin(href)
        if link_url.startswith(('http://', 'https://')):
            links.append(link_url)

    return data, links


async def main() -> None:
    # Enter the context of the Actor.
    async with Actor:
        # Retrieve the Actor input, and use default values if not provided.
        actor_input = await Actor.get_input() or {}
        start_urls = actor_input.get('startUrls', [{'url': 'https://crawlee.dev'}])
        max_depth = actor_input.get('maxDepth', 1)

        # Exit if no start URLs are provided.
        if not start_urls:
            Actor.log.info('No start URLs specified in Actor input, exiting...')
            await Actor.exit()

        # Create a proxy configuration that routes requests through Apify Proxy.
        proxy_configuration = await Actor.create_proxy_configuration()

        # Open the default request queue for handling URLs to be processed.
        request_queue = await Actor.open_request_queue()

        # Enqueue the start URLs. Their crawl depth defaults to 0.
        for start_url in start_urls:
            url = start_url.get('url')
            Actor.log.info(f'Enqueuing start URL: {url}')
            await request_queue.add_request(Request.from_url(url))

        # Process the URLs from the request queue.
        while request := await request_queue.fetch_next_request():
            url = request.url

            # Read the crawl depth tracked by the request itself.
            depth = request.crawl_depth
            Actor.log.info(f'Scraping {url} (depth={depth}) ...')

            try:
                # Get a fresh proxy URL for each request (None if no proxy set up).
                proxy_url = None
                if proxy_configuration:
                    proxy_url = await proxy_configuration.new_url()

                # Fetch the page and extract its data and nested links.
                data, links = await scrape_page(url, proxy_url=proxy_url)

                # Store the extracted data to the default dataset.
                await Actor.push_data(data)
                Actor.log.info(
                    f'Stored data from {url} '
                    f'(title={data["title"]!r}, {len(links)} links found).'
                )

                # If we are not too deep yet, enqueue the links we found one
                # level deeper than the current page.
                if depth < max_depth:
                    for link_url in links:
                        Actor.log.info(f'Enqueuing {link_url} ...')
                        new_request = Request.from_url(link_url)
                        new_request.crawl_depth = depth + 1
                        await request_queue.add_request(new_request)

            except Exception:
                Actor.log.exception(f'Cannot extract data from {url}.')

            finally:
                # Mark the request as handled so it is not processed again.
                await request_queue.mark_request_as_handled(request)


if __name__ == '__main__':
    asyncio.run(main())
