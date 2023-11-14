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

## Example

```python
from apify import Actor
from bs4 import BeautifulSoup
from httpx import AsyncClient

async def main() -> None:
    async with Actor:
        # Read the input parameters from the Actor input
        actor_input = await Actor.get_input()
        # Fetch the HTTP response from the specified URL
        async with AsyncClient() as client:
            response = await client.get(actor_input['url'])
        # Process the HTML content
        soup = BeautifulSoup(response.content, 'html.parser')
        # Push the extracted data
        await Actor.push_data({
            'url': actor_input['url'],
            'title': soup.title.string,
        })
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
