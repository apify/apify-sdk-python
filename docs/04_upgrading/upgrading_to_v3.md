---
id: upgrading-to-v3
title: Upgrading to v3
---

This page summarizes the breaking changes between Apify Python SDK v2.x and v3.0.

## Python version support

Support for Python 3.9 has been dropped. The Apify Python SDK v3.x now requires Python 3.10 or later. Make sure your environment is running a compatible version before upgrading.

## Changes in storages

Apify Python SDK v3.0 includes Crawlee v1.0, which brings significant changes to the storage APIs. In Crawlee v1.0, the `Dataset`, `KeyValueStore`, and `RequestQueue` storage APIs have been updated for consistency and simplicity. Below is a detailed overview of what's new, what's changed, and what's been removed.

See the Crawlee's [Storages guide](https://crawlee.dev/python/docs/guides/storages) for more details.

### Dataset

The `Dataset` API now includes several new methods, such as:

- `get_metadata` - retrieves metadata information for the dataset.
- `purge` - completely clears the dataset, including all items (keeps the metadata only).
- `list_items` - returns the dataset's items in a list format.

Some older methods have been removed or replaced:

- `from_storage_object` constructor has been removed. You should now use the `open` method with either a `name` or `id` parameter.
- `get_info` method and the `storage_object` property have been replaced by the new `get_metadata` method.
- `set_metadata` method has been removed.
- `write_to_json` and `write_to_csv` methods have been removed; instead, use the `export_to` method for exporting data in different formats.

### Key-value store

The `KeyValueStore` API now includes several new methods, such as:

- `get_metadata` - retrieves metadata information for the key-value store.
- `purge` - completely clears the key-value store, removing all keys and values (keeps the metadata only).
- `delete_value` - deletes a specific key and its associated value.
- `list_keys` - lists all keys in the key-value store.

Some older methods have been removed or replaced:

- `from_storage_object` - removed; use the `open` method with either a `name` or `id` instead.
- `get_info` and `storage_object` - replaced by the new `get_metadata` method.
- `set_metadata` method has been removed.

### Request queue

The `RequestQueue` API now includes several new methods, such as:

- `get_metadata` - retrieves metadata information for the request queue.
- `purge` - completely clears the request queue, including all pending and processed requests (keeps the metadata only).
- `add_requests` - replaces the previous `add_requests_batched` method, offering the same functionality under a simpler name.

Some older methods have been removed or replaced:

- `from_storage_object` - removed; use the `open` method with either a `name` or `id` instead.
- `get_info` and `storage_object` - replaced by the new `get_metadata` method.
- `get_request` has argument `unique_key` instead of `request_id` as the `id` field was removed from the `Request`.
- `set_metadata` method has been removed.

Some changes in the related model classes:

- `resource_directory` in `RequestQueueMetadata` - removed; use the corresponding `path_to_*` property instead.
- `stats` field in `RequestQueueMetadata` - removed as it was unused.
- `RequestQueueHead` - replaced by `RequestQueueHeadWithLocks`.

## Removed Actor.config property
- `Actor.config` property has been removed. Use `Actor.configuration` instead.

## Default storage ids in configuration changed to None
- `Configuration.default_key_value_store_id` changed from `'default'` to `None`.
- `Configuration.default_dataset_id` changed from `'default'` to `None`.
- `Configuration.default_request_queue_id` changed from `'default'` to `None`.

Previously using the default storage without specifying its `id` in `Configuration` would lead to using specific storage with id `'default'`. Now it will use newly created unnamed storage with `'id'` assigned by the Apify platform, consecutive calls to get the default storage will return the same storage.

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

### Changes in storage clients

## Explicit control over storage clients used in Actor
- It is now possible to have full control over which storage clients are used by the `Actor`. To make development of Actors convenient, the `Actor` has two storage clients. One that is used when running on Apify platform or when opening storages with `force_cloud=True` and the other client that is used when running outside the Apify platform. The `Actor` has reasonable defaults and for the majority of use-cases there is no need to change it. However, if you need to use a different storage client, you can set it up before entering `Actor` context through `service_locator`.

**Now (v3.0):**

```python
from crawlee import service_locator
from apify.storage_clients import ApifyStorageClient, SmartApifyStorageClient, MemoryStorageClient
from apify import Actor


async def main():
    service_locator.set_storage_client(
        SmartApifyStorageClient(
            cloud_storage_client=ApifyStorageClient(request_queue_access="single"),
            local_storage_client=MemoryStorageClient()
        )
    )
    async with Actor:
        rq = await Actor.open_request_queue()
```


## The default use of optimized ApifyRequestQueueClient

- The default client for working with Apify platform based `RequestQueue` is now optimized and simplified client which does significantly lower amount of API calls, but does not support multiple consumers working on the same queue. It is cheaper and faster and is suitable for the majority of the use cases.
- The full client is still available, but it has to be explicitly requested via `request_queue_access="shared"` argument when using the `ApifyStorageClient`.

**Now (v3.0):**

```python
from crawlee import service_locator
from apify.storage_clients import ApifyStorageClient, SmartApifyStorageClient
from apify import Actor


async def main():
    # Full client that supports multiple consumers of the Apify Request Queue
    service_locator.set_storage_client(
        SmartApifyStorageClient(
            cloud_storage_client=ApifyStorageClient(request_queue_access="shared"),
        )
    )
    async with Actor:
        rq = await Actor.open_request_queue()
```
