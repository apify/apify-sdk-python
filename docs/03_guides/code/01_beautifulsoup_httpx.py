import asyncio
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from apify import Actor, Request


async def scrape_page(
    client: httpx.AsyncClient, url: str
) -> tuple[dict[str, Any], list[str]]:
    """Fetch a single page with HTTPX and extract its data and links.

    Keeping the fetching and parsing in this helper keeps the Actor's main loop
    shallow. It returns the extracted data together with the links found on the
    page, so `main` only has to decide what to store and what to enqueue.
    """
    # Fetch the HTTP response from the specified URL using HTTPX.
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

    # Collect absolute links found on the page so the caller can enqueue them.
    links: list[str] = []
    for link in soup.find_all('a'):
        link_url = urljoin(url, link.get('href'))
        if link_url.startswith(('http://', 'https://')):
            links.append(link_url)

    return data, links


async def main() -> None:
    # Enter the context of the Actor.
    async with Actor:
        # Retrieve the Actor input, and use default values if not provided.
        actor_input = await Actor.get_input() or {}
        start_urls = actor_input.get('start_urls', [{'url': 'https://apify.com'}])
        max_depth = actor_input.get('max_depth', 1)

        # Exit if no start URLs are provided.
        if not start_urls:
            Actor.log.info('No start URLs specified in Actor input, exiting...')
            await Actor.exit()

        # Open the default request queue for handling URLs to be processed.
        request_queue = await Actor.open_request_queue()

        # Enqueue the start URLs. Their crawl depth defaults to 0.
        for start_url in start_urls:
            url = start_url.get('url')
            Actor.log.info(f'Enqueuing {url} ...')
            await request_queue.add_request(Request.from_url(url))

        # Create an HTTPX client to fetch the HTML content of the URLs.
        async with httpx.AsyncClient() as client:
            # Process the URLs from the request queue.
            while request := await request_queue.fetch_next_request():
                url = request.url

                # Read the crawl depth tracked by the request itself.
                depth = request.crawl_depth
                Actor.log.info(f'Scraping {url} (depth={depth}) ...')

                try:
                    # Fetch the page and extract its data and nested links.
                    data, links = await scrape_page(client, url)

                    # Store the extracted data to the default dataset.
                    await Actor.push_data(data)

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
