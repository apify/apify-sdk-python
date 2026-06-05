from __future__ import annotations

from scrapling.fetchers import AsyncFetcher

from apify import Actor, Request


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
            new_request = Request.from_url(url, user_data={'depth': 0})
            await request_queue.add_request(new_request)

        # Process the URLs from the request queue.
        while request := await request_queue.fetch_next_request():
            url = request.url

            if not isinstance(request.user_data['depth'], (str, int)):
                raise TypeError('Request.depth is an unexpected type.')

            depth = int(request.user_data['depth'])
            Actor.log.info(f'Scraping {url} (depth={depth}) ...')

            try:
                # Get a fresh proxy URL for each request (None if no proxy is set up).
                proxy_url = None
                if proxy_configuration:
                    proxy_url = await proxy_configuration.new_url()

                # Fetch the page with Scrapling's asynchronous HTTP fetcher. The
                # `impersonate` and `stealthy_headers` options make the request look
                # like it comes from a real Chrome browser, reducing the chance of
                # being blocked. The returned response is also a Scrapling selector.
                response = await AsyncFetcher.get(
                    url,
                    proxy=proxy_url,
                    impersonate='chrome',
                    stealthy_headers=True,
                    timeout=60,
                )

                # If the current depth is less than max_depth, find nested links
                # and enqueue them. The `::attr(href)` pseudo-selector reads the
                # attribute, and `response.urljoin` resolves it against the page URL.
                if depth < max_depth:
                    for link_href in response.css('a::attr(href)').getall():
                        link_url = response.urljoin(link_href)

                        if link_url.startswith(('http://', 'https://')):
                            Actor.log.info(f'Enqueuing {link_url} ...')
                            new_request = Request.from_url(
                                link_url,
                                user_data={'depth': depth + 1},
                            )
                            await request_queue.add_request(new_request)

                # Extract the desired data using Scrapling's CSS selectors. The
                # `::text` pseudo-element returns the text content of the elements.
                data = {
                    'url': url,
                    'title': response.css('title::text').get(),
                    'h1s': response.css('h1::text').getall(),
                    'h2s': response.css('h2::text').getall(),
                    'h3s': response.css('h3::text').getall(),
                }

                # Store the extracted data to the default dataset.
                await Actor.push_data(data)

            except Exception:
                Actor.log.exception(f'Cannot extract data from {url}.')

            finally:
                # Mark the request as handled to ensure it is not processed again.
                await request_queue.mark_request_as_handled(request)
