import asyncio
from typing import Any
from urllib.parse import urljoin

import impit
import parsel

from apify import Actor, Request


async def scrape_page(
    client: impit.AsyncClient, url: str
) -> tuple[dict[str, Any], list[str]]:
    """Fetch a single page with Impit and extract its data and links.

    Keeping the fetching and parsing in this helper keeps the Actor's main loop
    shallow. It returns the extracted data together with the links found on the
    page, so `main` only has to decide what to store and what to enqueue.
    """
    # Fetch the HTTP response from the specified URL using Impit.
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

    # Collect absolute links found on the page so the caller can enqueue them.
    links: list[str] = []
    for link_href in selector.css('a::attr(href)').getall():
        link_url = urljoin(url, link_href)
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

        # Create an Impit client to fetch the HTML content of the URLs.
        async with impit.AsyncClient() as client:
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
