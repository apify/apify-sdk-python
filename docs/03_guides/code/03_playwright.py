import asyncio
from typing import Any
from urllib.parse import urljoin, urlsplit

from playwright.async_api import BrowserContext, async_playwright

from apify import Actor, Request
from apify.storages import RequestQueue

# To run locally, install the browsers first: `playwright install --with-deps`.
# On the Apify platform they are already in the Actor's Docker image.


def to_playwright_proxy(proxy_url: str) -> dict[str, str]:
    """Split an Apify Proxy URL into Playwright's server/username/password."""
    parts = urlsplit(proxy_url)
    return {
        'server': f'{parts.scheme}://{parts.hostname}:{parts.port}',
        'username': parts.username or '',
        'password': parts.password or '',
    }


async def scrape_page(
    context: BrowserContext, url: str
) -> tuple[dict[str, Any], list[str]]:
    """Open the URL in a new page and return its data and same-site links."""
    page = await context.new_page()
    try:
        await page.goto(url)

        data = {
            'url': url,
            'title': await page.title(),
            'h1s': [await h1.text_content() for h1 in await page.locator('h1').all()],
            'h2s': [await h2.text_content() for h2 in await page.locator('h2').all()],
            'h3s': [await h3.text_content() for h3 in await page.locator('h3').all()],
        }

        # Keep only absolute links on the same host.
        links: list[str] = []
        host = urlsplit(url).netloc
        for link in await page.locator('a').all():
            link_href = await link.get_attribute('href')
            link_url = urljoin(url, link_href)
            if not link_url.startswith(('http://', 'https://')):
                continue
            if urlsplit(link_url).netloc == host:
                links.append(link_url)

        return data, links

    finally:
        await page.close()


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

        # Playwright proxies at the browser level, so one URL is shared per run.
        proxy_configuration = await Actor.create_proxy_configuration()
        proxy_url = await proxy_configuration.new_url() if proxy_configuration else None

        # Open the request queue and enqueue the start URLs (crawl depth 0).
        request_queue = await Actor.open_request_queue()
        for start_url in start_urls:
            url = start_url.get('url')
            Actor.log.info(f'Enqueuing start URL: {url}')
            await request_queue.add_request(Request.from_url(url))

        # Cap the crawl; raise or remove to follow more pages.
        max_requests = 50
        handled_requests = 0

        Actor.log.info('Launching Playwright...')

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=Actor.configuration.headless,
                proxy=to_playwright_proxy(proxy_url) if proxy_url else None,
                args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
            )
            context = await browser.new_context()

            while handled_requests < max_requests and (
                request := await request_queue.fetch_next_request()
            ):
                handled_requests += 1
                url = request.url
                depth = request.crawl_depth
                Actor.log.info(f'Scraping {url} (depth={depth}) ...')

                try:
                    data, links = await scrape_page(context, url)
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
