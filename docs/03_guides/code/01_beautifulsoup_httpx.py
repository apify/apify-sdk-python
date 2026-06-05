import asyncio
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from apify import Actor, Request


async def scrape_page(
    url: str,
    *,
    proxy_url: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Fetch a single page with HTTPX and extract its data and links.

    A fresh client is created per call, so each request can go through a new
    proxy URL and a different IP address. The helper returns the extracted data
    together with the links found on the page, so `main` only has to decide what
    to store and what to enqueue.
    """
    # Fetch the HTTP response from the specified URL using HTTPX, optionally
    # routing the request through the provided Apify Proxy URL.
    async with httpx.AsyncClient(proxy=proxy_url) as client:
        response = await client.get(url, follow_redirects=True)

    # Parse the HTML content using Beautiful Soup.
    soup = BeautifulSoup(response.content, 'html.parser')

    # Extract the desired data.
    data = {
        'url': url,
        'title': soup.title.string if soup.title else None,
        'h1s': [h1.text for h1 in soup.find_all('h1')],
        'h2s': [h2.text for h2 in soup.find_all('h2')],
        'h3s': [h3.text for h3 in soup.find_all('h3')],
    }

    # Collect absolute links on the same host so the crawl stays on this site.
    links: list[str] = []
    host = urlsplit(url).netloc
    for link in soup.find_all('a'):
        link_url = urljoin(url, link.get('href'))
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
