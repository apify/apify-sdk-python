from __future__ import annotations

from typing import Any

from scrapling.fetchers import DynamicFetcher


async def scrape_page(
    url: str,
    *,
    proxy_url: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Fetch a single page in a real browser and extract its data and links.

    `DynamicFetcher` drives a real browser via Playwright, so it can render
    JavaScript-heavy pages. `network_idle` waits until the page stops making
    network requests before the HTML is captured. Apart from the fetcher call,
    everything else - including the parsing - is identical to the HTTP version.
    """
    response = await DynamicFetcher.async_fetch(
        url,
        proxy=proxy_url,
        headless=True,
        network_idle=True,
    )

    # Extract the desired data using CSS selectors. The `::text` pseudo-element
    # returns the text content of the matched elements.
    data = {
        'url': url,
        'title': response.css('title::text').get(),
        'h1s': response.css('h1::text').getall(),
        'h2s': response.css('h2::text').getall(),
        'h3s': response.css('h3::text').getall(),
    }

    # Collect absolute links from the page. The `::attr(href)` pseudo-selector
    # reads the attribute and `response.urljoin` resolves it against the page URL.
    links: list[str] = []
    for href in response.css('a::attr(href)').getall():
        link_url = response.urljoin(href)
        if link_url.startswith(('http://', 'https://')):
            links.append(link_url)

    return data, links
