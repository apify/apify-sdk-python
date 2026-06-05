from typing import Any

from scrapling.fetchers import DynamicFetcher


async def scrape_page(
    url: str,
    *,
    proxy_url: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Fetch a page in a real browser with Scrapling and return data and links."""
    # `network_idle` waits until the page stops making network requests.
    response = await DynamicFetcher.async_fetch(
        url,
        proxy=proxy_url,
        headless=True,
        network_idle=True,
    )

    data = {
        'url': url,
        'title': response.css('title::text').get(),
        'h1s': response.css('h1::text').getall(),
        'h2s': response.css('h2::text').getall(),
        'h3s': response.css('h3::text').getall(),
    }

    # Collect absolute links from the page.
    links: list[str] = []
    for href in response.css('a::attr(href)').getall():
        link_url = response.urljoin(href)
        if link_url.startswith(('http://', 'https://')):
            links.append(link_url)

    return data, links
