from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup
from httpx import AsyncClient

from apify import Actor, Request


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

        # Enqueue the start URLs with an initial crawl depth of 0.
        for start_url in start_urls:
            url = start_url.get('url')
            Actor.log.info(f'Enqueuing {url} ...')
            new_request = Request.from_url(url, user_data={'depth': 0})
            await request_queue.add_request(new_request)

        # Create an HTTPX client to fetch the HTML content of the URLs.
        async with AsyncClient() as client:
            # Process the URLs from the request queue.
            while request := await request_queue.fetch_next_request():
                url = request.url

                if not isinstance(request.user_data['depth'], (str, int)):
                    raise TypeError('Request.depth is an enexpected type.')

                depth = int(request.user_data['depth'])
                Actor.log.info(f'Scraping {url} (depth={depth}) ...')

                try:
                    # Fetch the HTTP response from the specified URL using HTTPX.
                    response = await client.get(url, follow_redirects=True)

                    # Parse the HTML content using Beautiful Soup.
                    soup = BeautifulSoup(response.content, 'html.parser')

                    # If the current depth is less than max_depth, find nested links
                    # and enqueue them.
                    if depth < max_depth:
                        for link in soup.find_all('a'):
                            link_href = link.get('href')
                            link_url = urljoin(url, link_href)

                            if link_url.startswith(('http://', 'https://')):
                                Actor.log.info(f'Enqueuing {link_url} ...')
                                new_request = Request.from_url(
                                    link_url,
                                    user_data={'depth': depth + 1},
                                )
                                await request_queue.add_request(new_request)

                    # Extract the desired data.
                    data = {
                        'url': url,
                        'title': soup.title.string if soup.title else None,
                        'h1s': [h1.text for h1 in soup.find_all('h1')],
                        'h2s': [h2.text for h2 in soup.find_all('h2')],
                        'h3s': [h3.text for h3 in soup.find_all('h3')],
                    }

                    # Store the extracted data to the default dataset.
                    await Actor.push_data(data)

                except Exception:
                    Actor.log.exception(f'Cannot extract data from {url}.')

                finally:
                    # Mark the request as handled to ensure it is not processed again.
                    await request_queue.mark_request_as_handled(new_request)
