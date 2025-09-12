---
id: upgrading-to-v3
title: Upgrading to v3
---

This page summarizes the breaking changes between Apify Python SDK v2.x and v3.0.

## Python version support

Support for Python 3.9 has been dropped. The Apify Python SDK v3.x now requires Python 3.10 or later. Make sure your environment is running a compatible version before upgrading.

## Storages

<!-- TODO -->

## Storage clients

<!-- TODO -->

## The default use of optimized ApifyRequestQueueClient

- The default client for working with Apify platform based `RequestQueue` is now optimized and simplified client which has significantly lower amount of API calls, but does not support multiple consumers working on the same queue. It is cheaper and faster and is suitable for the majority of the use cases.
- The full client is still available, but it has to be explicitly requested via `simple_request_queue=False` argument when using the `ApifyStorageClient`.

**Before (v2.x):**

```python
from apify import Actor

async def main():
    async with Actor:
        ...
```

**Now (v3.0):**

```python
from apify import Actor
from crawlee import service_locator
from apify.storage_clients import ApifyStorageClient

async def main():
    # Use the full-featured RequestQueue client only if you really need it.
    service_locator.set_storage_client(ApifyStorageClient(simple_request_queue=False))
    async with Actor:
        ...
```
