---
id: upgrading-to-v2
title: Upgrading to v2
---

This page summarizes the breaking changes between Apify Python SDK v1.x and v2.0.

## Python version support

Support for Python 3.8 has been dropped. The Apify Python SDK v2.x now requires Python 3.9 or later. Make sure your environment is running a compatible version before upgrading.

## Storages

- The SDK now uses [crawlee](https://github.com/apify/crawlee-python) for local storage emulation. This change should not affect intended usage (working with `Dataset`, `KeyValueStore` and `RequestQueue` classes from the `apify.storages` module or using the shortcuts exposed by the `Actor` class) in any way.
- There is a difference in the `RequestQueue.add_request` method: it accepts an `apify.Request` object instead of a free-form dictionary.
    - A quick way to migrate from dict-based arguments is to wrap it with a `Request.model_validate()` call.
    - The preferred way is using the `Request.from_url` helper which prefills the `unique_key` and `id` attributes, or instantiating it directly, e.g., `Request(url='https://example.tld', ...)`.
    - For simple use cases, `add_request` also accepts plain strings that contain an URL, e.g. `queue.add_request('https://example.tld')`.
- Removing the `StorageClientManager` class is a significant change. If you need to change the storage client, use `crawlee.service_container` instead.

## Configuration

The `apify.Configuration` class now uses `pydantic_settings` to load configuration from environment variables. This eliminates the need for the helper functions which handled environment variables in `apify._utils`.

Attributes suffixed with `_millis` were renamed to remove said suffix and have the `datetime.timedelta` type now.

## Actor

- The `Actor.main` method has been removed as it brings no benefits compared to using `async with Actor`.
- The `Actor.add_webhook`, `Actor.start`, `Actor.call` and `Actor.start_task` methods now accept instances of the `apify.Webhook` model instead of an untyped `dict`.
- `Actor.start`, `Actor.call`, `Actor.start_task`, `Actor.set_status_message` and `Actor.abort` return instances of the `ActorRun` model instead of an untyped `dict`.
- Upon entering the context manager (`async with Actor`), the `Actor` puts the default logging configuration in place. This can be disabled using the `configure_logging` parameter.
- The `config` parameter of `Actor` has been renamed to `configuration`.
- Event handlers registered via `Actor.on` will now receive Pydantic objects instead of untyped dicts. For example, where you would do `event['isMigrating']`, you should now use `event.is_migrating`

## Scrapy integration

The `apify.scrapy.utils.open_queue_with_custom_client` function is not necessary anymore and has been removed.

## Subpackage visibility

The following modules were made private:

- `apify.proxy_configuration` (`ProxyConfiguration` is still exported from `apify`)
- `apify.config` (`Configuration` is still exported from `apify`)
- `apify.actor` (`Actor` is still exported from `apify`)
- `apify.event_manager`
- `apify.consts`
