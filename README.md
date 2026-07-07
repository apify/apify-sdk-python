<h1 align="center">Apify SDK for Python</h1>

<p align="center">
  <strong>The official Python SDK for building <a href="https://docs.apify.com/platform/actors">Apify Actors</a>.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/apify/"><img src="https://badge.fury.io/py/apify.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/apify/"><img src="https://img.shields.io/pypi/dm/apify" alt="PyPI downloads"></a>
  <a href="https://pypi.org/project/apify/"><img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python versions"></a>
  <a href="https://github.com/apify/apify-sdk-python/actions/workflows/on_master.yaml"><img src="https://github.com/apify/apify-sdk-python/actions/workflows/on_master.yaml/badge.svg?branch=master" alt="Build status"></a>
  <a href="https://codecov.io/gh/apify/apify-sdk-python"><img src="https://codecov.io/gh/apify/apify-sdk-python/graph/badge.svg?token=Y6JBIZQFT6" alt="Coverage"></a>
  <a href="https://github.com/apify/apify-sdk-python/blob/master/LICENSE"><img src="https://img.shields.io/pypi/l/apify" alt="License"></a>
  <a href="https://discord.gg/jyEM2PRvMU"><img src="https://img.shields.io/discord/801163717915574323?label=discord" alt="Chat on Discord"></a>
</p>

`apify` is the official SDK for building [Apify Actors](https://docs.apify.com/platform/actors) in Python. It handles the Actor lifecycle, [storage](https://docs.apify.com/platform/storage) access, platform events, [Apify Proxy](https://docs.apify.com/platform/proxy), pay-per-event charging, and more.

> If you only need to **consume** the [Apify API](https://docs.apify.com/api/v2) from Python (running Actors, reading datasets, managing storages) rather than building Actors, use the [Apify API client for Python](https://docs.apify.com/api/client/python) instead. It comes bundled with this SDK.

## Table of contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [What are Actors?](#what-are-actors)
- [Features](#features)
- [What you can build](#what-you-can-build)
- [Usage examples](#usage-examples)
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

## What are Actors?

Actors are serverless programs that can do almost anything. From simple scripts and web scrapers to complex automation workflows, AI agents, or even always-on services that expose HTTP endpoints.

They can run either locally or on the Apify platform, where you can scale their execution, monitor runs, schedule tasks, integrate them with other services, or even publish and monetize them. If you're new to Apify, learn more about the platform in the [Apify documentation](https://docs.apify.com/platform/about).

For more context, read the [Actor whitepaper](https://whitepaper.actor/).

## Features

- Run the full Actor lifecycle inside `async with Actor:`, covering init, exit, failures, status messages, and reboots ([Actor lifecycle](https://docs.apify.com/sdk/python/docs/concepts/actor-lifecycle)).
- Read Actor input validated against your input schema with `Actor.get_input()` ([Actor input](https://docs.apify.com/sdk/python/docs/concepts/actor-input)).
- Read and write datasets, key-value stores, and request queues, locally or on the platform ([Working with storages](https://docs.apify.com/sdk/python/docs/concepts/storages)).
- React to platform events such as system info, migration, and abort ([Actor events](https://docs.apify.com/sdk/python/docs/concepts/actor-events)).
- Route requests through Apify Proxy with group selection, country targeting, and rotation ([Proxy management](https://docs.apify.com/sdk/python/docs/concepts/proxy-management)).
- Start, call, abort, and metamorph other Actors and tasks, and attach webhooks to run events ([Interacting with other Actors](https://docs.apify.com/sdk/python/docs/concepts/interacting-with-other-actors), [Webhooks](https://docs.apify.com/sdk/python/docs/concepts/webhooks)).
- Monetize your Actor with pay-per-event charging ([Pay-per-event](https://docs.apify.com/sdk/python/docs/concepts/pay-per-event)).
- Reach the full [Apify API](https://docs.apify.com/api/v2) through a preconfigured `ApifyClient` ([Accessing the Apify API](https://docs.apify.com/sdk/python/docs/concepts/access-apify-api)).

## What you can build

Almost any Python project can become an Actor, including projects for:

- **Web scraping and crawling** — The SDK is fully compatible with [Crawlee](https://crawlee.dev/python), which makes Apify a natural place to deploy and scale your crawlers (see the [Crawlee guide](https://docs.apify.com/sdk/python/docs/guides/crawlee)). It also works with other popular scraping libraries, such as [Scrapy](https://docs.apify.com/sdk/python/docs/guides/scrapy), [Scrapling](https://docs.apify.com/sdk/python/docs/guides/scrapling), or [Crawl4AI](https://docs.apify.com/sdk/python/docs/guides/crawl4ai).
- **Browser automation** — Drive a real browser with [Playwright](https://docs.apify.com/sdk/python/docs/guides/playwright) or [Selenium](https://docs.apify.com/sdk/python/docs/guides/selenium), or with higher-level tools such as [Browser Use](https://docs.apify.com/sdk/python/docs/guides/browser-use).
- **Web servers and APIs** — Run a [web server](https://docs.apify.com/sdk/python/docs/guides/running-webserver) inside an Actor to serve HTTP requests, for example to expose your scraper as a live API.
- **AI agents** — Host agents built with your framework of choice (see the [AI agents guide](https://docs.apify.com/sdk/python/docs/guides/ai-agents)). Ready-made Actor templates cover [LangGraph](https://apify.com/templates/python-langgraph), [CrewAI](https://apify.com/templates/python-crewai), [PydanticAI](https://apify.com/templates/python-pydanticai), [LlamaIndex](https://apify.com/templates/python-llamaindex-agent), and [Smolagents](https://apify.com/templates/python-smolagents).
- **MCP servers** — Deploy a Python MCP server as an Actor and make its tools available to any MCP client (see the [MCP servers guide](https://docs.apify.com/sdk/python/docs/guides/mcp-servers)). Ready-made Actor templates cover the [MCP server](https://apify.com/templates/python-mcp-empty) and [MCP proxy](https://apify.com/templates/python-mcp-proxy).

Whatever you build, the Apify SDK doesn't lock you into a particular framework. Bring the libraries you already use, and let Apify run your project in the cloud.

## Usage examples

The examples below show two common setups, but the same `async with Actor:` pattern works with any stack. For more, see the [guides](https://docs.apify.com/sdk/python/docs/guides/beautifulsoup-httpx).

### HTTPX with BeautifulSoup

Scrape pages with [HTTPX](https://www.python-httpx.org/) and [BeautifulSoup](https://pypi.org/project/beautifulsoup4/), using the Actor's request queue to track URLs:

```python
from bs4 import BeautifulSoup
from httpx import AsyncClient

from apify import Actor


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        start_urls = actor_input.get('start_urls', [{'url': 'https://apify.com'}])

        # Enqueue the start URLs into the default request queue.
        request_queue = await Actor.open_request_queue()
        for start_url in start_urls:
            await request_queue.add_request(start_url['url'])

        # Process the queue until it's empty.
        while request := await request_queue.fetch_next_request():
            Actor.log.info(f'Scraping {request.url} ...')
            async with AsyncClient() as client:
                response = await client.get(request.url)
            soup = BeautifulSoup(response.content, 'html.parser')

            # Push the extracted data to the default dataset.
            await Actor.push_data({
                'url': request.url,
                'title': soup.title.string if soup.title else None,
            })
```

### Crawlee with Playwright

Scrape pages with [Crawlee](https://crawlee.dev/python)'s `PlaywrightCrawler`, which handles queueing, concurrency, and the browser for you:

```python
from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext

from apify import Actor


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        start_urls = [url['url'] for url in actor_input.get('start_urls', [{'url': 'https://apify.com'}])]

        crawler = PlaywrightCrawler(max_requests_per_crawl=50, headless=True)

        @crawler.router.default_handler
        async def handler(context: PlaywrightCrawlingContext) -> None:
            Actor.log.info(f'Scraping {context.request.url} ...')
            await context.push_data({
                'url': context.request.url,
                'title': await context.page.title(),
            })
            # Follow links found on the page.
            await context.enqueue_links()

        await crawler.run(start_urls)
```

## Documentation

The full SDK documentation lives at **[docs.apify.com/sdk/python](https://docs.apify.com/sdk/python)**. For the Apify platform itself, see the [Apify documentation](https://docs.apify.com/).

| Section | What you'll find |
| --- | --- |
| [Overview](https://docs.apify.com/sdk/python/docs/overview) | What the SDK is, what Actors are, and how the pieces fit together. |
| [Quick start](https://docs.apify.com/sdk/python/docs/quick-start) | Create, run, and deploy your first Python Actor. |
| [Concepts](https://docs.apify.com/sdk/python/docs/concepts/actor-lifecycle) | Actor lifecycle, input, storages, events, proxy management, interacting with other Actors, webhooks, accessing the Apify API, logging, configuration, and pay-per-event. |
| [Guides](https://docs.apify.com/sdk/python/docs/guides/beautifulsoup-httpx) | Integrations with BeautifulSoup, Parsel, Playwright, Selenium, Crawlee, Scrapy, Scrapling, Crawl4AI, and Browser Use, plus using uv, validating input with Pydantic, running a web server, building MCP servers, and hosting AI agents. |
| [Upgrading](https://docs.apify.com/sdk/python/docs/upgrading/upgrading-to-v4) | Migrating between major versions. |
| [API reference](https://docs.apify.com/sdk/python/reference) | Generated reference for every class and method. |
| [Changelog](https://docs.apify.com/sdk/python/docs/changelog) | Release history and breaking changes. |

## Related projects

- **[Apify API client for Python](https://docs.apify.com/api/client/python)** — talk to the Apify API directly from Python (bundled with this SDK).
- **[Crawlee for Python](https://crawlee.dev/python)** — web scraping and browser automation framework; fully compatible with this SDK.
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
