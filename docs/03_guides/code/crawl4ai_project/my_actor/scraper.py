from __future__ import annotations

from typing import TYPE_CHECKING, Any

from crawl4ai import CacheMode, CrawlerRunConfig, ProxyConfig

if TYPE_CHECKING:
    from crawl4ai import AsyncWebCrawler


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
