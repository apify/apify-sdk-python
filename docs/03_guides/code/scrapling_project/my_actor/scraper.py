from __future__ import annotations

from typing import Any

from scrapling.fetchers import AsyncFetcher


async def scrape_page(
    url: str,
    *,
    proxy_url: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Fetch a single page with Scrapling and extract its data and links.

    The page is fetched with Scrapling's asynchronous HTTP fetcher. The
    `impersonate` and `stealthy_headers` options make the request look like it
    comes from a real Chrome browser, which reduces the chance of being blocked.
    The returned response is also a Scrapling selector, so it can be queried with
    CSS selectors directly.
    """
    response = await AsyncFetcher.get(
        url,
        proxy=proxy_url,
        impersonate='chrome',
        stealthy_headers=True,
        timeout=60,
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
