---
id: upgrading-to-v20
title: Upgrading to v2.0
---

This page summarizes most of the breaking changes between Apify Python SDK v1.x and v2.0.

## Storages

The SDK now uses [crawlee](https://github.com/apify/crawlee-python) for local storage emulation. This change should not affect intended usage (working with `Dataset`, `KeyValueStore` and `RequestQueue` classes from the `apify.storages` module or using the shortcuts exposed by the `Actor` class) in any way.

Removing the `StorageClientManager` class is a significant change. If you need to change the storage client, use `crawlee.service_container` instead.

## Configuration

The `apify.Configuration` class now uses `pydantic_settings` to load configuration from environment variables. This eliminates the need for the helper functions which handled environment variables in `apify._utils`.

Attributes suffixed with `_millis` were renamed to remove said suffix and have the `datetime.timedelta` type now.

## Actor

- The `Actor.main` method has been removed as it brings no benefits compared to using `async with Actor`.
- The `Actor.add_webhook`, `Actor.start`, `Actor.call` and `Actor.start_task` methods now accept instances of the `apify.Webhook` model instead of an untyped `dict`.
- `Actor.start`, `Actor.call`, `Actor.start_task`, `Actor.set_status_message` and `Actor.abort` return instances of the `ActorRun` model instead of an untyped `dict`.

## Scrapy integration

The `apify.scrapy.utils.open_queue_with_custom_client` function is not necessary anymore and has been removed.

## Subpackage visibility

The following modules were made private:

- `apify.proxy_configuration` (`ProxyConfiguration` is still exported from `apify`)
- `apify.config` (`Configuration` is still exported from `apify`)
- `apify.actor` (`Actor` is still exported from `apify`)
- `apify.event_manager`
- `apify.consts`
