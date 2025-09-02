from __future__ import annotations

import asyncio
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


async def main() -> None:
    # Enter the context of the Actor.
    async with Actor:
        # Retrieve the Actor input, and use default values if not provided.
        actor_input = await Actor.get_input() or {}
        start_urls = actor_input.get('start_urls', [{'url': 'https://apify.com'}])
        max_depth = actor_input.get('max_depth', 1)

        # Exit if no start URLs are provided.
        if not start_urls:
            Actor.log.info('No start URLs specified in actor input, exiting...')
            await Actor.exit()

        # Open the default request queue for handling URLs to be processed.
        request_queue = await Actor.open_request_queue()

        # Enqueue the start URLs with an initial crawl depth of 0.
        for start_url in start_urls:
            url = start_url.get('url')
            Actor.log.info(f'Enqueuing {url} ...')
            new_request = Request.from_url(url, user_data={'depth': 0})
            await request_queue.add_request(new_request)

        # Launch a new Selenium Chrome WebDriver and configure it.
        Actor.log.info('Launching Chrome WebDriver...')
        chrome_options = ChromeOptions()

        if Actor.config.headless:
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

            if not isinstance(request.user_data['depth'], (str, int)):
                raise TypeError('Request.depth is an enexpected type.')

            depth = int(request.user_data['depth'])
            Actor.log.info(f'Scraping {url} (depth={depth}) ...')

            try:
                # Navigate to the URL using Selenium WebDriver. Use asyncio.to_thread
                # for non-blocking execution.
                await asyncio.to_thread(driver.get, url)

                # If the current depth is less than max_depth, find nested links
                # and enqueue them.
                if depth < max_depth:
                    for link in driver.find_elements(By.TAG_NAME, 'a'):
                        link_href = link.get_attribute('href')
                        link_url = urljoin(url, link_href)

                        if link_url.startswith(('http://', 'https://')):
                            Actor.log.info(f'Enqueuing {link_url} ...')
                            new_request = Request.from_url(
                                link_url,
                                user_data={'depth': depth + 1},
                            )
                            await request_queue.add_request(new_request)

                # Extract the desired data.
                data = {
                    'url': url,
                    'title': driver.title,
                }

                # Store the extracted data to the default dataset.
                await Actor.push_data(data)

            except Exception:
                Actor.log.exception(f'Cannot extract data from {url}.')

            finally:
                # Mark the request as handled to ensure it is not processed again.
                await request_queue.mark_request_as_handled(request)

        driver.quit()
