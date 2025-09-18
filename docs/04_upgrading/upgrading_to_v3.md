---
id: upgrading-to-v3
title: Upgrading to v3
---

This page summarizes the breaking changes between Apify Python SDK v2.x and v3.0.

## Python version support

Support for Python 3.9 has been dropped. The Apify Python SDK v3.x now requires Python 3.10 or later. Make sure your environment is running a compatible version before upgrading.

## Actor initialization and ServiceLocator changes

`Actor` initialization and global `service_locator` services setup is more strict and predictable.
- Services in `Actor` can't be changed after calling `Actor.init`, entering the `async with Actor` context manager or after requesting them from the `Actor`
- Services in `Actor` can be different from services in Crawler


**Now (v3.0):**

```python
from crawlee.crawlers import BasicCrawler
from crawlee.storage_clients import MemoryStorageClient
from crawlee.configuration import Configuration
from crawlee.events import LocalEventManager
from apify import Actor

async def main():

    async with Actor():
        # This crawler will use same services as Actor and global service_locator
        crawler_1 = BasicCrawler()

        # This crawler will use custom services
        custom_configuration = Configuration()
        custom_event_manager = LocalEventManager.from_config(custom_configuration)
        custom_storage_client = MemoryStorageClient()
        crawler_2 = BasicCrawler(
            configuration=custom_configuration,
            event_manager=custom_event_manager,
            storage_client=custom_storage_client,
        )
```

## Removed Actor.config property
- `Actor.config` property has been removed. Use `Actor.configuration` instead.

## Storages

<!-- TODO -->

## Storage clients

<!-- TODO -->
