import asyncio
from typing import Any
from urllib.parse import urljoin, urlsplit

from playwright.async_api import BrowserContext, async_playwright

from apify import Actor, Request

# Note: To run this Actor locally, ensure that Playwright browsers are installed.
# Run `playwright install --with-deps` in the Actor's virtual environment to install them.
# When running on the Apify platform, these dependencies are already included
# in the Actor's Docker image.


def to_playwright_proxy(proxy_url: str) -> dict[str, str]:
    """Convert an Apify Proxy URL into Playwright proxy settings.

    Playwright wants the proxy as a `server` URL with the credentials in separate
    `username` and `password` fields, so the single URL returned by
    `ProxyConfiguration.new_url` has to be split into its parts.
    """
    parts = urlsplit(proxy_url)
    return {
        'server': f'{parts.scheme}://{parts.hostname}:{parts.port}',
        'username': parts.username or '',
        'password': parts.password or '',
    }


async def scrape_page(
    context: BrowserContext, url: str
) -> tuple[dict[str, Any], list[str]]:
    """Open a page in the browser, extract its data, and collect its links.

    Keeping the page handling in this helper keeps the Actor's main loop shallow.
    It returns the extracted data together with the links found on the page, so
    `main` only has to decide what to store and what to enqueue.
    """
    page = await context.new_page()
    try:
        await page.goto(url)

        # Extract the desired data.
        data = {
            'url': url,
            'title': await page.title(),
            'h1s': [await h1.text_content() for h1 in await page.locator('h1').all()],
            'h2s': [await h2.text_content() for h2 in await page.locator('h2').all()],
            'h3s': [await h3.text_content() for h3 in await page.locator('h3').all()],
        }

        # Collect absolute links found on the page so the caller can enqueue them.
        links: list[str] = []
        for link in await page.locator('a').all():
            link_href = await link.get_attribute('href')
            link_url = urljoin(url, link_href)
            if link_url.startswith(('http://', 'https://')):
                links.append(link_url)

        return data, links

    finally:
        await page.close()


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

        # Create a proxy configuration that routes the browser through Apify Proxy.
        # Playwright applies the proxy at the browser level, so the whole run shares
        # a single proxy URL rather than rotating it per request.
        proxy_configuration = await Actor.create_proxy_configuration()
        proxy_url = await proxy_configuration.new_url() if proxy_configuration else None

        # Open the default request queue for handling URLs to be processed.
        request_queue = await Actor.open_request_queue()

        # Enqueue the start URLs. Their crawl depth defaults to 0.
        for start_url in start_urls:
            url = start_url.get('url')
            Actor.log.info(f'Enqueuing start URL: {url}')
            await request_queue.add_request(Request.from_url(url))

        Actor.log.info('Launching Playwright...')

        # Launch Playwright and open a new browser context.
        async with async_playwright() as playwright:
            # Configure the browser to launch in headless mode as per Actor configuration.
            browser = await playwright.chromium.launch(
                headless=Actor.configuration.headless,
                proxy=to_playwright_proxy(proxy_url) if proxy_url else None,
                args=['--disable-gpu'],
            )
            context = await browser.new_context()

            # Process the URLs from the request queue.
            while request := await request_queue.fetch_next_request():
                url = request.url

                # Read the crawl depth tracked by the request itself.
                depth = request.crawl_depth
                Actor.log.info(f'Scraping {url} (depth={depth}) ...')

                try:
                    # Fetch the page and extract its data and nested links.
                    data, links = await scrape_page(context, url)

                    # Store the extracted data to the default dataset.
                    await Actor.push_data(data)
                    Actor.log.info(
                        f'Stored data from {url} '
                        f'(title={data["title"]!r}, {len(links)} links found).'
                    )

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
