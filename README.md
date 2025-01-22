# Apify SDK for Python

The Apify SDK for Python is the official library to create [Apify Actors](https://docs.apify.com/platform/actors)
in Python. It provides useful features like Actor lifecycle management, local storage emulation, and Actor
event handling.

If you just need to access the [Apify API](https://docs.apify.com/api/v2) from your Python applications,
check out the [Apify Client for Python](https://docs.apify.com/api/client/python) instead.

## Installation

The Apify SDK for Python is available on PyPI as the `apify` package.
For default installation, using Pip, run the following:

```bash
pip install apify
```

For users interested in integrating Apify with Scrapy, we provide a package extra called `scrapy`.
To install Apify with the `scrapy` extra, use the following command:

```bash
pip install apify[scrapy]
```

## Documentation

For usage instructions, check the documentation on [Apify Docs](https://docs.apify.com/sdk/python/).

## Examples

Below are few examples demonstrating how to use the Apify SDK with some web scraping-related libraries.

### Apify SDK with HTTPX and BeautifulSoup

This example illustrates how to integrate the Apify SDK with [HTTPX](https://www.python-httpx.org/) and [BeautifulSoup](https://pypi.org/project/beautifulsoup4/) to scrape data from web pages.

```python
from bs4 import BeautifulSoup
from httpx import AsyncClient

from apify import Actor


async def main() -> None:
    async with Actor:
        # Retrieve the Actor input, and use default values if not provided.
        actor_input = await Actor.get_input() or {}
        start_urls = actor_input.get('start_urls', [{'url': 'https://apify.com'}])

        # Open the default request queue for handling URLs to be processed.
        request_queue = await Actor.open_request_queue()

        # Enqueue the start URLs.
        for start_url in start_urls:
            url = start_url.get('url')
            await request_queue.add_request(url)

        # Process the URLs from the request queue.
        while request := await request_queue.fetch_next_request():
            Actor.log.info(f'Scraping {request.url} ...')

            # Fetch the HTTP response from the specified URL using HTTPX.
            async with AsyncClient() as client:
                response = await client.get(request.url)

            # Parse the HTML content using Beautiful Soup.
            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract the desired data.
            data = {
                'url': actor_input['url'],
                'title': soup.title.string,
                'h1s': [h1.text for h1 in soup.find_all('h1')],
                'h2s': [h2.text for h2 in soup.find_all('h2')],
                'h3s': [h3.text for h3 in soup.find_all('h3')],
            }

            # Store the extracted data to the default dataset.
            await Actor.push_data(data)
```

### Apify SDK with PlaywrightCrawler from Crawlee

This example demonstrates how to use the Apify SDK alongside `PlaywrightCrawler` from [Crawlee](https://crawlee.dev/python) to perform web scraping.

```python
from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext

from apify import Actor


async def main() -> None:
    async with Actor:
        # Retrieve the Actor input, and use default values if not provided.
        actor_input = await Actor.get_input() or {}
        start_urls = [url.get('url') for url in actor_input.get('start_urls', [{'url': 'https://apify.com'}])]

        # Exit if no start URLs are provided.
        if not start_urls:
            Actor.log.info('No start URLs specified in Actor input, exiting...')
            await Actor.exit()

        # Create a crawler.
        crawler = PlaywrightCrawler(
            # Limit the crawl to max requests. Remove or increase it for crawling all links.
            max_requests_per_crawl=50,
            headless=True,
        )

        # Define a request handler, which will be called for every request.
        @crawler.router.default_handler
        async def request_handler(context: PlaywrightCrawlingContext) -> None:
            url = context.request.url
            Actor.log.info(f'Scraping {url}...')

            # Extract the desired data.
            data = {
                'url': context.request.url,
                'title': await context.page.title(),
                'h1s': [await h1.text_content() for h1 in await context.page.locator('h1').all()],
                'h2s': [await h2.text_content() for h2 in await context.page.locator('h2').all()],
                'h3s': [await h3.text_content() for h3 in await context.page.locator('h3').all()],
            }

            # Store the extracted data to the default dataset.
            await context.push_data(data)

            # Enqueue additional links found on the current page.
            await context.enqueue_links()

        # Run the crawler with the starting URLs.
        await crawler.run(start_urls)
```

## What are Actors?

Actors are serverless cloud programs that can do almost anything a human can do in a web browser.
They can do anything from small tasks such as filling in forms or unsubscribing from online services,
all the way up to scraping and processing vast numbers of web pages.

They can be run either locally, or on the [Apify platform](https://docs.apify.com/platform/),
where you can run them at scale, monitor them, schedule them, or publish and monetize them.

If you're new to Apify, learn [what is Apify](https://docs.apify.com/platform/about)
in the Apify platform documentation.

## Creating Actors

To create and run Actors through Apify Console,
see the [Console documentation](https://docs.apify.com/academy/getting-started/creating-actors#choose-your-template).

To create and run Python Actors locally, check the documentation for
[how to create and run Python Actors locally](https://docs.apify.com/sdk/python/docs/overview/running-locally).

## Guides

To see how you can use the Apify SDK with other popular libraries used for web scraping,
check out our guides for using
[Requests and HTTPX](https://docs.apify.com/sdk/python/docs/guides/requests-and-httpx),
[Beautiful Soup](https://docs.apify.com/sdk/python/docs/guides/beautiful-soup),
[Playwright](https://docs.apify.com/sdk/python/docs/guides/playwright),
[Selenium](https://docs.apify.com/sdk/python/docs/guides/selenium),
or [Scrapy](https://docs.apify.com/sdk/python/docs/guides/scrapy).

## Usage concepts

To learn more about the features of the Apify SDK and how to use them,
check out the Usage Concepts section in the sidebar,
particularly the guides for the [Actor lifecycle](https://docs.apify.com/sdk/python/docs/concepts/actor-lifecycle),
[working with storages](https://docs.apify.com/sdk/python/docs/concepts/storages),
[handling Actor events](https://docs.apify.com/sdk/python/docs/concepts/actor-events)
or [how to use proxies](https://docs.apify.com/sdk/python/docs/concepts/proxy-management).
