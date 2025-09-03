import asyncio
from urllib.parse import urljoin

import impit
import parsel

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

        # Create an Impit client to fetch the HTML content of the URLs.
        async with impit.AsyncClient() as client:
            # Process the URLs from the request queue.
            while request := await request_queue.fetch_next_request():
                url = request.url

                if not isinstance(request.user_data['depth'], (str, int)):
                    raise TypeError('Request.depth is an unexpected type.')

                depth = int(request.user_data['depth'])
                Actor.log.info(f'Scraping {url} (depth={depth}) ...')

                try:
                    # Fetch the HTTP response from the specified URL using Impit.
                    response = await client.get(url)

                    # Parse the HTML content using Parsel Selector.
                    selector = parsel.Selector(text=response.text)

                    # If the current depth is less than max_depth, find nested links
                    # and enqueue them.
                    if depth < max_depth:
                        # Extract all links using CSS selector
                        links = selector.css('a::attr(href)').getall()
                        for link_href in links:
                            link_url = urljoin(url, link_href)

                            if link_url.startswith(('http://', 'https://')):
                                Actor.log.info(f'Enqueuing {link_url} ...')
                                new_request = Request.from_url(
                                    link_url,
                                    user_data={'depth': depth + 1},
                                )
                                await request_queue.add_request(new_request)

                    # Extract the desired data using Parsel selectors.
                    title = selector.css('title::text').get()
                    h1s = selector.css('h1::text').getall()
                    h2s = selector.css('h2::text').getall()
                    h3s = selector.css('h3::text').getall()

                    data = {
                        'url': url,
                        'title': title,
                        'h1s': h1s,
                        'h2s': h2s,
                        'h3s': h3s,
                    }

                    # Store the extracted data to the default dataset.
                    await Actor.push_data(data)

                except Exception:
                    Actor.log.exception(f'Cannot extract data from {url}.')

                finally:
                    # Mark the request as handled to ensure it is not processed again.
                    await request_queue.mark_request_as_handled(request)


if __name__ == '__main__':
    asyncio.run(main())
