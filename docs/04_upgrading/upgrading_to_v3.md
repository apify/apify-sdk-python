---
id: upgrading-to-v3
title: Upgrading to v3
---

This page summarizes the breaking changes between Apify Python SDK v2.x and v3.0.

## Python version support

Support for Python 3.9 has been dropped. The Apify Python SDK v3.x now requires Python 3.10 or later. Make sure your environment is running a compatible version before upgrading.

## Actor initialization and ServiceLocator changes

`Actor` initialization and global `service_locator` services setup is more strict and predictable.
- Services in `Actor` can't be changed after calling `Actor.init`, entering the `async with Actor` context manager or after requesting them from the `Actor`.
- Services in `Actor` can be different from services in Crawler.


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

## Explicit control over storage clients used in Actor
- It is now possible to have full control over which storage clients are used by the `Actor`. To make development of Actors convenient, the `Actor` has two storage clients. One that is used when running on Apify platform or when opening storages with `force_cloud=True` and the other client that is used when running outside the Apify platform. The `Actor` has reasonable defaults and for the majority of use-cases there is no need to change it. However, if you need to use a different storage client, you can set it up before entering `Actor` context through `service_locator`.

**Now (v3.0):**
```python
from crawlee import service_locator
from apify.storage_clients import ApifyStorageClient, ApifyHybridStorageClient, MemoryStorageClient
from apify import Actor


async def main():
    service_locator.set_storage_client(
        ApifyHybridStorageClient(
            cloud_storage_client=ApifyStorageClient(access="single"),
            local_storage_client=MemoryStorageClient()
        )
    )
    async with Actor:
        rq = await Actor.open_request_queue()
```


## The default use of optimized ApifyRequestQueueClient

- The default client for working with Apify platform based `RequestQueue` is now optimized and simplified client which does significantly lower amount of API calls, but does not support multiple consumers working on the same queue. It is cheaper and faster and is suitable for the majority of the use cases.
- The full client is still available, but it has to be explicitly requested via `access="shared"` argument when using the `ApifyStorageClient`.

**Now (v3.0):**

```python
from crawlee import service_locator
from apify.storage_clients import ApifyStorageClient
from apify import Actor

async def main():
   # Full client that supports multiple consumers of the Apify Request Queue
    service_locator.set_storage_client(ApifyStorageClient(access="shared"))
    async with Actor:
        rq = await Actor.open_request_queue()
```
