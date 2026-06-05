import asyncio
from typing import Any
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By

from apify import Actor, Request

# To run this Actor locally, you need to have the Selenium Chromedriver installed.
# Follow the installation guide at:
# https://www.selenium.dev/documentation/webdriver/getting_started/install_drivers/
# When running on the Apify platform, the Chromedriver is already included
# in the Actor's Docker image.


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
        start_urls = actor_input.get('start_urls', [{'url': 'https://apify.com'}])
        max_depth = actor_input.get('max_depth', 1)

        # Exit if no start URLs are provided.
        if not start_urls:
            Actor.log.info('No start URLs specified in Actor input, exiting...')
            await Actor.exit()

        # Open the default request queue for handling URLs to be processed.
        request_queue = await Actor.open_request_queue()

        # Enqueue the start URLs. Their crawl depth defaults to 0.
        for start_url in start_urls:
            url = start_url.get('url')
            Actor.log.info(f'Enqueuing {url} ...')
            await request_queue.add_request(Request.from_url(url))

        # Launch a new Selenium Chrome WebDriver and configure it.
        Actor.log.info('Launching Chrome WebDriver...')
        chrome_options = ChromeOptions()

        if Actor.configuration.headless:
            chrome_options.add_argument('--headless')

        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        driver = webdriver.Chrome(options=chrome_options)

        # Test WebDriver setup by navigating to an example page.
        driver.get('http://www.example.com')
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
