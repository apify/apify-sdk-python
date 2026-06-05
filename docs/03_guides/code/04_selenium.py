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

# To run this Actor locally, you need to have the Selenium Chromedriver installed.
# Follow the installation guide at:
# https://www.selenium.dev/documentation/webdriver/getting_started/install_drivers/
# When running on the Apify platform, the Chromedriver is already included
# in the Actor's Docker image.


def proxy_auth_extension(proxy_url: str) -> str:
    """Build a temporary Chrome extension that routes Chrome through a proxy.

    Chrome ignores credentials passed in the `--proxy-server` flag, so an
    authenticated proxy such as Apify Proxy has to be configured from inside an
    extension: its service worker sets the proxy server and answers the browser's
    authentication challenge with the username and password. The function returns
    the path to a packed extension ready to be loaded with `add_extension`.
    """
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

    # The service worker sets the proxy server and supplies the credentials when
    # Chrome is challenged for authentication. `json.dumps` handles the escaping.
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


def scrape_page(driver: webdriver.Chrome, url: str) -> tuple[dict[str, Any], list[str]]:
    """Navigate to a page with Selenium, extract its data, and collect its links.

    These are blocking WebDriver calls, so the Actor's main loop runs this helper
    in a worker thread via `asyncio.to_thread`. It returns the extracted data
    together with the links found on the page, so `main` only has to decide what
    to store and what to enqueue.
    """
    driver.get(url)

    # Extract the desired data.
    data = {
        'url': url,
        'title': driver.title,
        'h1s': [el.text for el in driver.find_elements(By.TAG_NAME, 'h1')],
        'h2s': [el.text for el in driver.find_elements(By.TAG_NAME, 'h2')],
        'h3s': [el.text for el in driver.find_elements(By.TAG_NAME, 'h3')],
    }

    # Collect absolute links found on the page so the caller can enqueue them.
    links: list[str] = []
    for link in driver.find_elements(By.TAG_NAME, 'a'):
        link_url = urljoin(url, link.get_attribute('href'))
        if link_url.startswith(('http://', 'https://')):
            links.append(link_url)

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

        # Open the default request queue for handling URLs to be processed.
        request_queue = await Actor.open_request_queue()

        # Enqueue the start URLs. Their crawl depth defaults to 0.
        for start_url in start_urls:
            url = start_url.get('url')
            Actor.log.info(f'Enqueuing start URL: {url}')
            await request_queue.add_request(Request.from_url(url))

        # Launch a new Selenium Chrome WebDriver and configure it.
        Actor.log.info('Launching Chrome WebDriver...')
        chrome_options = ChromeOptions()

        if Actor.configuration.headless:
            # The new headless mode is required for the proxy extension to load.
            chrome_options.add_argument('--headless=new')

        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')

        # Route the browser through Apify Proxy. Selenium applies the proxy at the
        # browser level, so the whole run shares a single proxy URL.
        proxy_configuration = await Actor.create_proxy_configuration()
        if proxy_configuration and (proxy_url := await proxy_configuration.new_url()):
            chrome_options.add_extension(proxy_auth_extension(proxy_url))
            chrome_options.add_argument(
                '--disable-features=DisableLoadExtensionCommandLineSwitch'
            )

        driver = webdriver.Chrome(options=chrome_options)

        # Test WebDriver setup by navigating to an example page.
        driver.get('https://example.com')
        if driver.title != 'Example Domain':
            raise ValueError('Failed to open example page.')

        # Process the URLs from the request queue.
        while request := await request_queue.fetch_next_request():
            url = request.url

            # Read the crawl depth tracked by the request itself.
            depth = request.crawl_depth
            Actor.log.info(f'Scraping {url} (depth={depth}) ...')

            try:
                # Fetch the page and extract its data and nested links. The blocking
                # WebDriver calls run in a worker thread to keep the loop responsive.
                data, links = await asyncio.to_thread(scrape_page, driver, url)

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

        driver.quit()


if __name__ == '__main__':
    asyncio.run(main())
