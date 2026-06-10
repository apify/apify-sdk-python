<h1 align="center">Apify SDK for Python</h1>

<p align="center">
  <strong>The official Python SDK for building <a href="https://docs.apify.com/platform/actors">Apify Actors</a>.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/apify/"><img src="https://badge.fury.io/py/apify.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/apify/"><img src="https://img.shields.io/pypi/dm/apify" alt="PyPI downloads"></a>
  <a href="https://pypi.org/project/apify/"><img src="https://img.shields.io/pypi/pyversions/apify" alt="Python versions"></a>
  <a href="https://codecov.io/gh/apify/apify-sdk-python"><img src="https://codecov.io/gh/apify/apify-sdk-python/graph/badge.svg?token=Y6JBIZQFT6" alt="Coverage"></a>
  <a href="https://github.com/apify/apify-sdk-python/blob/master/LICENSE"><img src="https://img.shields.io/pypi/l/apify" alt="License"></a>
  <a href="https://discord.gg/jyEM2PRvMU"><img src="https://img.shields.io/discord/801163717915574323?label=discord" alt="Chat on Discord"></a>
</p>

`apify` is the official SDK for building [Apify Actors](https://docs.apify.com/platform/actors) in Python. Actors are serverless programs that run on the [Apify platform](https://apify.com), where you can scale them, schedule them, and monetize them. The SDK manages the Actor lifecycle, gives you access to [storages](https://docs.apify.com/platform/storage) (datasets, key-value stores, request queues), handles platform events, configures [Apify Proxy](https://docs.apify.com/platform/proxy), and supports pay-per-event monetization. It builds on the [Crawlee](https://crawlee.dev/python) web scraping framework and bundles the [Apify API client](https://docs.apify.com/api/client/python).

> If you only need to **consume** the [Apify API](https://docs.apify.com/api/v2) from Python (running Actors, reading datasets, managing storages) rather than building Actors, use the [Apify API client for Python](https://docs.apify.com/api/client/python) instead. It comes bundled with this SDK.

## Table of contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [Features](#features)
- [Usage examples](#usage-examples)
- [What are Actors?](#what-are-actors)
- [Documentation](#documentation)
- [Related projects](#related-projects)
- [Support and community](#support-and-community)
- [Contributing](#contributing)
- [License](#license)

## Installation

The Apify SDK for Python requires **Python 3.11 or higher**. It is published on [PyPI](https://pypi.org/project/apify/) as the `apify` package and can be installed with [pip](https://pip.pypa.io/):

```bash
pip install apify
```

or with [uv](https://docs.astral.sh/uv/):

```bash
uv add apify
```

To use the Scrapy integration, install the `scrapy` extra:

```bash
pip install 'apify[scrapy]'
```

## Quick start

An Actor is a Python program that runs inside the `async with Actor:` context. The context initializes the Actor when it starts and tears it down when it finishes. Here's a minimal Actor that reads its input and stores a result:

```python
from apify import Actor


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input()
        Actor.log.info('Actor input: %s', actor_input)
        await Actor.set_value('OUTPUT', 'Hello, world!')
```

The quickest way to scaffold a full Actor project, with the `.actor` configuration, input schema, and Dockerfile already in place, is the [Apify CLI](https://docs.apify.com/cli):

1. Install the CLI:

    ```bash
    npm install -g apify-cli
    ```

2. Create a new Actor from the Python "getting started" template:

    ```bash
    apify create my-actor --template python-start
    ```

3. Run it locally:

    ```bash
    cd my-actor
    apify run
    ```

To create, run, and deploy your first Actor step by step, see the [Quick start guide](https://docs.apify.com/sdk/python/docs/quick-start).

## Features

- **Actor lifecycle management** — `async with Actor:` initializes the Actor, then handles exit, failure, status messages, and reboots ([Actor lifecycle](https://docs.apify.com/sdk/python/docs/concepts/actor-lifecycle)).
- **Typed Actor input** — read input validated against your input schema with `Actor.get_input()` ([Actor input](https://docs.apify.com/sdk/python/docs/concepts/actor-input)).
- **Storage access** — read and write datasets, key-value stores, and request queues, both locally and on the platform ([Working with storages](https://docs.apify.com/sdk/python/docs/concepts/storages)).
- **Platform events** — react to system info, migration, and abort events streamed over a WebSocket ([Actor events](https://docs.apify.com/sdk/python/docs/concepts/actor-events)).
- **Proxy management** — route requests through Apify Proxy with residential or datacenter groups, country targeting, and rotation ([Proxy management](https://docs.apify.com/sdk/python/docs/concepts/proxy-management)).
- **Actor orchestration** — start, call, abort, and metamorph other Actors and tasks, and register webhooks for run events ([Interacting with other Actors](https://docs.apify.com/sdk/python/docs/concepts/interacting-with-other-actors), [Webhooks](https://docs.apify.com/sdk/python/docs/concepts/webhooks)).
- **Pay-per-event monetization** — charge for the events your Actor emits ([Pay-per-event](https://docs.apify.com/sdk/python/docs/concepts/pay-per-event)).
- **Direct Apify API access** — reach the full [Apify API](https://docs.apify.com/api/v2) through a preconfigured [`ApifyClient`](https://docs.apify.com/api/client/python) ([Accessing the Apify API](https://docs.apify.com/sdk/python/docs/concepts/access-apify-api)).
- **Built on Crawlee** — combine the SDK with [Crawlee](https://crawlee.dev/python) crawlers, or any HTTP or browser library you prefer ([Crawlee guide](https://docs.apify.com/sdk/python/docs/guides/crawlee)).
- **Scrapy integration** — run existing Scrapy spiders as Apify Actors through the `apify[scrapy]` extra ([Scrapy guide](https://docs.apify.com/sdk/python/docs/guides/scrapy)).

## Usage examples

The SDK works with whatever scraping stack you prefer. The examples below show two common setups. For more, see the [Guides](https://docs.apify.com/sdk/python/docs/guides/beautifulsoup-httpx).

### HTTPX with BeautifulSoup

Scrape pages with [HTTPX](https://www.python-httpx.org/) and [BeautifulSoup](https://pypi.org/project/beautifulsoup4/), using the Actor's request queue to track URLs:

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
                'url': request.url,
                'title': soup.title.string,
                'h1s': [h1.text for h1 in soup.find_all('h1')],
                'h2s': [h2.text for h2 in soup.find_all('h2')],
                'h3s': [h3.text for h3 in soup.find_all('h3')],
            }

            # Store the extracted data to the default dataset.
            await Actor.push_data(data)
```

### PlaywrightCrawler from Crawlee

Scrape pages with [Crawlee](https://crawlee.dev/python)'s `PlaywrightCrawler`, which handles queueing, concurrency, and browser automation for you:

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

Actors are serverless cloud programs that can do almost anything a human can do in a web browser. They range from small tasks, such as filling in forms or unsubscribing from online services, all the way up to scraping and processing vast numbers of web pages.

They run either locally or on the [Apify platform](https://docs.apify.com/platform/), where you can run them at scale, monitor them, schedule them, or publish and monetize them. If you're new to Apify, learn [what Apify is](https://docs.apify.com/platform/about) in the platform documentation.

## Documentation

The full documentation lives at **[docs.apify.com/sdk/python](https://docs.apify.com/sdk/python)**.

| Section | What you'll find |
|---|---|
| [Overview](https://docs.apify.com/sdk/python/docs/overview) | What the SDK is, what Actors are, and how the pieces fit together. |
| [Quick start](https://docs.apify.com/sdk/python/docs/quick-start) | Create, run, and deploy your first Python Actor. |
| [Concepts](https://docs.apify.com/sdk/python/docs/concepts/actor-lifecycle) | Actor lifecycle, input, storages, events, proxy management, interacting with other Actors, webhooks, accessing the Apify API, logging, configuration, and pay-per-event. |
| [Guides](https://docs.apify.com/sdk/python/docs/guides/beautifulsoup-httpx) | Integrations with BeautifulSoup, Parsel, Playwright, Selenium, Crawlee, Scrapy, Crawl4AI, and Browser Use, plus running a web server and using uv. |
| [Upgrading](https://docs.apify.com/sdk/python/docs/upgrading/upgrading-to-v4) | Migrating between major versions. |
| [API reference](https://docs.apify.com/sdk/python/reference) | Generated reference for every class and method. |
| [Changelog](https://docs.apify.com/sdk/python/docs/changelog) | Release history and breaking changes. |

## Related projects

- **[Apify API client for Python](https://docs.apify.com/api/client/python)** — talk to the Apify API directly from Python (bundled with this SDK).
- **[Crawlee for Python](https://crawlee.dev/python)** — the web scraping and browser automation framework the SDK builds on.
- **[Apify SDK for JavaScript / TypeScript](https://docs.apify.com/sdk/js)** — the equivalent SDK for Node.js.
- **[Apify API client for JavaScript / TypeScript](https://docs.apify.com/api/client/js)** — the equivalent API client for Node.js.
- **[Crawlee for JavaScript / TypeScript](https://crawlee.dev)** — the original Node.js implementation of Crawlee.
- **[Apify CLI](https://docs.apify.com/cli)** — command-line tool for creating, running, and deploying Actors locally and on the platform.

## Support and community

- **Discord** — chat with the team and other users on the [Apify Discord server](https://discord.gg/jyEM2PRvMU).
- **GitHub issues** — report a bug or request a feature in the [issue tracker](https://github.com/apify/apify-sdk-python/issues).

## Contributing

Bug reports, fixes, and improvements are welcome! See [CONTRIBUTING.md](./CONTRIBUTING.md) for the development setup, coding standards, testing, and release process. The project uses [uv](https://docs.astral.sh/uv/) for project management and [Poe the Poet](https://poethepoet.natn.io/) as a task runner; the typical loop is:

```bash
uv run poe install-dev   # install dev dependencies and git hooks
uv run poe check-code    # lint, type-check, and unit tests
```

## License

Released under the [Apache License 2.0](./LICENSE).
