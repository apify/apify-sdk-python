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


async def scrape_page(
    crawler: AsyncWebCrawler,
    url: str,
    *,
    proxy_url: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Crawl a single page with Crawl4AI and extract its markdown and links.

    The page is rendered in the browser managed by `crawler`, and Crawl4AI turns
    the result into clean, LLM-ready markdown. Setting `proxy_config` on the
    per-request `CrawlerRunConfig` routes this request through Apify Proxy, so
    every page can use a fresh IP address.
    """
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        proxy_config=ProxyConfig.from_string(proxy_url) if proxy_url else None,
    )

    result = await crawler.arun(url, config=run_config)
    if not result.success:
        raise RuntimeError(result.error_message or f'Failed to crawl {url}')

    # `result.markdown` is the rendered page as clean markdown, and
    # `result.metadata` carries page-level fields such as the title.
    data = {
        'url': result.url,
        'title': (result.metadata or {}).get('title'),
        'markdown': str(result.markdown),
    }

    # Crawl4AI already splits links into `internal` (same site) and `external`.
    # We follow only the internal ones to keep the crawl on the same website.
    internal_links = result.links.get('internal', [])
    links = [link['href'] for link in internal_links if link.get('href')]

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

        # Configure the headless browser that Crawl4AI drives.
        browser_config = BrowserConfig(headless=True)

        # Open a single browser-backed crawler and reuse it for every request.
        async with AsyncWebCrawler(config=browser_config) as crawler:
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

                    # Crawl the page and extract its markdown and nested links.
                    data, links = await scrape_page(crawler, url, proxy_url=proxy_url)

                    # Store the extracted data to the default dataset.
                    await Actor.push_data(data)
                    Actor.log.info(
                        f'Stored data from {url} '
                        f'(title={data["title"]!r}, {len(links)} links found).'
                    )

                    # If we are not too deep yet, enqueue the links we found one
                    # level deeper than the current page.
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
