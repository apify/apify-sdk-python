import asyncio
from typing import Any
from urllib.parse import urljoin, urlsplit

import impit
import parsel

from apify import Actor, Request


async def scrape_page(
    url: str,
    *,
    proxy_url: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Fetch a single page with Impit and extract its data and links.

    A fresh client is created per call, so each request can go through a new
    proxy URL and a different IP address. The helper returns the extracted data
    together with the links found on the page, so `main` only has to decide what
    to store and what to enqueue.
    """
    # Fetch the HTTP response from the specified URL using Impit, optionally
    # routing the request through the provided Apify Proxy URL.
    async with impit.AsyncClient(proxy=proxy_url) as client:
        response = await client.get(url)

    # Parse the HTML content using a Parsel selector.
    selector = parsel.Selector(text=response.text)

    # Extract the desired data using Parsel selectors.
    data = {
        'url': url,
        'title': selector.css('title::text').get(),
        'h1s': selector.css('h1::text').getall(),
        'h2s': selector.css('h2::text').getall(),
        'h3s': selector.css('h3::text').getall(),
    }

    # Collect absolute links on the same host so the crawl stays on this site.
    links: list[str] = []
    host = urlsplit(url).netloc
    for link_href in selector.css('a::attr(href)').getall():
        link_url = urljoin(url, link_href)
        if not link_url.startswith(('http://', 'https://')):
            continue
        if urlsplit(link_url).netloc == host:
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

        # Limit the crawl; raise or remove the cap to follow more pages.
        max_requests = 50
        handled_requests = 0

        # Process the URLs from the request queue, up to the request limit.
        while handled_requests < max_requests and (
            request := await request_queue.fetch_next_request()
        ):
            handled_requests += 1
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

                # If we are not too deep yet, enqueue the links we found.
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
