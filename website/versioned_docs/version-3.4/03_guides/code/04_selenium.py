import asyncio
import json
from pathlib import Path
from tempfile import mkdtemp
from typing import Any
from urllib.parse import urljoin, urlsplit
from zipfile import ZipFile

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By

from apify import Actor, Request
from apify.storages import RequestQueue

# To run locally, install the Selenium Chromedriver:
# https://www.selenium.dev/documentation/webdriver/getting_started/install_drivers/
# On the Apify platform, it's already in the Actor's Docker image.


def proxy_auth_extension(proxy_url: str) -> str:
    """Build a Chrome extension that routes Chrome through an authenticated proxy."""
    parts = urlsplit(proxy_url)

    manifest = {
        'name': 'Apify Proxy',
        'version': '1.0.0',
        'manifest_version': 3,
        'permissions': ['proxy', 'webRequest', 'webRequestAuthProvider'],
        'host_permissions': ['<all_urls>'],
        'background': {'service_worker': 'background.js'},
        'minimum_chrome_version': '108',
    }

    # The service worker sets the proxy and answers the auth challenge.
    proxy_config = json.dumps(
        {
            'mode': 'fixed_servers',
            'rules': {
                'singleProxy': {
                    'scheme': parts.scheme,
                    'host': parts.hostname,
                    'port': parts.port,
                },
            },
        }
    )
    credentials = json.dumps(
        {'username': parts.username or '', 'password': parts.password or ''}
    )
    background = (
        'chrome.proxy.settings.set('
        '{value: ' + proxy_config + ', scope: "regular"});\n'
        'chrome.webRequest.onAuthRequired.addListener(\n'
        '    () => ({authCredentials: ' + credentials + '}),\n'
        '    {urls: ["<all_urls>"]},\n'
        '    ["blocking"],\n'
        ');\n'
    )

    extension_path = Path(mkdtemp()) / 'apify_proxy.zip'
    with ZipFile(extension_path, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('background.js', background)
    return str(extension_path)


def build_chrome_driver(proxy_url: str | None = None) -> webdriver.Chrome:
    """Create a headless Chrome WebDriver, optionally routed through a proxy."""
    chrome_options = ChromeOptions()

    if Actor.configuration.headless:
        # The new headless mode is required to load the proxy extension.
        chrome_options.add_argument('--headless=new')

    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')

    if proxy_url:
        chrome_options.add_extension(proxy_auth_extension(proxy_url))
        chrome_options.add_argument(
            '--disable-features=DisableLoadExtensionCommandLineSwitch'
        )

    return webdriver.Chrome(options=chrome_options)


def scrape_page(driver: webdriver.Chrome, url: str) -> tuple[dict[str, Any], list[str]]:
    """Navigate to the URL with Selenium and return its data and same-site links."""
    driver.get(url)

    data = {
        'url': url,
        'title': driver.title,
        'h1s': [el.text for el in driver.find_elements(By.TAG_NAME, 'h1')],
        'h2s': [el.text for el in driver.find_elements(By.TAG_NAME, 'h2')],
        'h3s': [el.text for el in driver.find_elements(By.TAG_NAME, 'h3')],
    }

    # Keep only absolute links on the same host.
    links: list[str] = []
    host = urlsplit(url).netloc
    for link in driver.find_elements(By.TAG_NAME, 'a'):
        link_url = urljoin(url, link.get_attribute('href'))
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

        # Selenium proxies at the browser level, so one URL is shared per run.
        proxy_configuration = await Actor.create_proxy_configuration()

        # Open the request queue and enqueue the start URLs (crawl depth 0).
        request_queue = await Actor.open_request_queue()
        for start_url in start_urls:
            url = start_url.get('url')
            Actor.log.info(f'Enqueuing start URL: {url}')
            await request_queue.add_request(Request.from_url(url))

        # Cap the crawl. Raise or remove the limit to follow more pages.
        max_requests = 50
        handled_requests = 0

        # Fresh proxy URL for the run (None if no proxy).
        proxy_url = None
        if proxy_configuration:
            proxy_url = await proxy_configuration.new_url()

        Actor.log.info('Launching Chrome WebDriver...')
        driver = build_chrome_driver(proxy_url)

        while handled_requests < max_requests and (
            request := await request_queue.fetch_next_request()
        ):
            handled_requests += 1
            url = request.url
            depth = request.crawl_depth
            Actor.log.info(f'Scraping {url} (depth={depth}) ...')

            try:
                # Blocking WebDriver calls run in a worker thread.
                data, links = await asyncio.to_thread(scrape_page, driver, url)
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

        driver.quit()


if __name__ == '__main__':
    asyncio.run(main())
