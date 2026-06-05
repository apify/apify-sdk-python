from __future__ import annotations

from apify import Actor, Request

from .scraper import scrape_page


async def main() -> None:
    # Enter the context of the Actor.
    async with Actor:
        # Retrieve the Actor input, and use default values if not provided.
        actor_input = await Actor.get_input() or {}
        start_urls = actor_input.get('start_urls', [{'url': 'https://crawlee.dev'}])
        max_depth = actor_input.get('max_depth', 1)

        # Exit if no start URLs are provided.
        if not start_urls:
            Actor.log.info('No start URLs specified in Actor input, exiting...')
            await Actor.exit()

        # Create a proxy configuration that routes requests through Apify Proxy.
        proxy_configuration = await Actor.create_proxy_configuration()

        # Open the default request queue for handling URLs to be processed.
        request_queue = await Actor.open_request_queue()

        # Enqueue the start URLs with an initial crawl depth of 0.
        for start_url in start_urls:
            url = start_url.get('url')
            Actor.log.info(f'Enqueuing {url} ...')
            request = Request.from_url(url, user_data={'depth': 0})
            await request_queue.add_request(request)

        # Process the URLs from the request queue.
        while request := await request_queue.fetch_next_request():
            url = request.url

            if not isinstance(request.user_data['depth'], (str, int)):
                raise TypeError('Request.depth is an unexpected type.')

            depth = int(request.user_data['depth'])
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

                # If we are not too deep yet, enqueue the links we found.
                if depth < max_depth:
                    for link_url in links:
                        Actor.log.info(f'Enqueuing {link_url} ...')
                        new_request = Request.from_url(
                            link_url,
                            user_data={'depth': depth + 1},
                        )
                        await request_queue.add_request(new_request)

            except Exception:
                Actor.log.exception(f'Cannot extract data from {url}.')

            finally:
                # Mark the request as handled so it is not processed again.
                await request_queue.mark_request_as_handled(request)
