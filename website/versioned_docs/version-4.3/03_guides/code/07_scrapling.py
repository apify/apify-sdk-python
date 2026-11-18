import asyncio
from typing import Any
from urllib.parse import urlsplit

from scrapling.fetchers import AsyncFetcher

from apify import Actor, Request
from apify.storages import RequestQueue


async def scrape_page(
    url: str,
    *,
    proxy_url: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Fetch a page with Scrapling's HTTP fetcher and return data and links."""
    # `impersonate` and `stealthy_headers` make the request look like Chrome.
    response = await AsyncFetcher.get(
        url,
        proxy=proxy_url,
        impersonate='chrome',
        stealthy_headers=True,
        timeout=60,
    )

    data = {
        'url': url,
        'title': response.css('title::text').get(),
        'h1s': response.css('h1::text').getall(),
        'h2s': response.css('h2::text').getall(),
        'h3s': response.css('h3::text').getall(),
    }

    # Keep only absolute links on the same host.
    links: list[str] = []
    host = urlsplit(url).netloc
    for href in response.css('a::attr(href)').getall():
        link_url = response.urljoin(href)
        if not link_url.startswith(('http://', 'https://')):
            continue
        if urlsplit(link_url).netloc == host:
            links.append(link_url)

    return data, links


async def enqueue_links(
    request_queue: RequestQueue,
    links: list[str],
    *,
    depth: int,
    max_depth: int,
) -> None:
    """Enqueue the links one level deeper, unless max_depth was reached."""
    if depth >= max_depth:
        return

    for link_url in links:
        Actor.log.info(f'Enqueuing {link_url} ...')
        request = Request.from_url(link_url)
        request.crawl_depth = depth + 1
        await request_queue.add_request(request)


async def main() -> None:
    async with Actor:
        # Read the Actor input.
        actor_input = await Actor.get_input() or {}
        start_urls = actor_input.get('startUrls', [{'url': 'https://crawlee.dev'}])
        max_depth = actor_input.get('maxDepth', 1)

        if not start_urls:
            Actor.log.info('No start URLs specified in Actor input, exiting...')
            await Actor.exit()

        # Set up Apify Proxy and the request queue.
        proxy_configuration = await Actor.create_proxy_configuration()
        request_queue = await Actor.open_request_queue()

        # Enqueue the start URLs (crawl depth defaults to 0).
        for start_url in start_urls:
            url = start_url.get('url')
            Actor.log.info(f'Enqueuing start URL: {url}')
            await request_queue.add_request(Request.from_url(url))

        # Cap the crawl. Raise or remove the limit to follow more pages.
        max_requests = 10
        handled_requests = 0

        while handled_requests < max_requests and (
            request := await request_queue.fetch_next_request()
        ):
            handled_requests += 1
            url = request.url
            depth = request.crawl_depth
            Actor.log.info(f'Scraping {url} (depth={depth}) ...')

            try:
                # Fresh proxy URL per request (None if no proxy).
                proxy_url = None
                if proxy_configuration:
                    proxy_url = await proxy_configuration.new_url()

                data, links = await scrape_page(url, proxy_url=proxy_url)
                await Actor.push_data(data)
                Actor.log.info(
                    f'Stored data from {url} '
                    f'(title={data["title"]!r}, {len(links)} links found).'
                )
                await enqueue_links(
                    request_queue, links, depth=depth, max_depth=max_depth
                )

            except Exception:
                Actor.log.exception(f'Cannot extract data from {url}.')

            finally:
                await request_queue.mark_request_as_handled(request)


if __name__ == '__main__':
    asyncio.run(main())
