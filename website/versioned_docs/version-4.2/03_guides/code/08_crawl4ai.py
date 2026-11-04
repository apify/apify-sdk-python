import asyncio
from typing import Any

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
    ProxyConfig,
)

from apify import Actor, Request
from apify.storages import RequestQueue


async def scrape_page(
    crawler: AsyncWebCrawler,
    url: str,
    *,
    proxy_url: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Crawl a page with Crawl4AI and return its markdown and same-site links."""
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        proxy_config=ProxyConfig.from_string(proxy_url) if proxy_url else None,
    )

    result = await crawler.arun(url, config=run_config)
    if not result.success:
        raise RuntimeError(result.error_message or f'Failed to crawl {url}')

    data = {
        'url': result.url,
        'title': (result.metadata or {}).get('title'),
        'markdown': str(result.markdown),
    }

    # Crawl4AI already classifies links; follow only the internal ones.
    internal_links = result.links.get('internal', [])
    links = [link['href'] for link in internal_links if link.get('href')]

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

        # Cap the crawl; raise or remove to follow more pages.
        max_requests = 10
        handled_requests = 0

        # Reuse one headless browser-backed crawler for every request.
        browser_config = BrowserConfig(headless=True)

        async with AsyncWebCrawler(config=browser_config) as crawler:
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

                    data, links = await scrape_page(crawler, url, proxy_url=proxy_url)
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
