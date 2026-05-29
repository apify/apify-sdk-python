---
id: upgrading-to-v4
title: Upgrading to v4
description: Breaking changes and migration guide from Apify SDK v3.x to v4.0.
---

This guide lists the breaking changes between Apify Python SDK v3.x and v4.0.

## Python 3.11+ required

Support for Python 3.10 has been dropped. The Apify Python SDK v4.x now requires Python 3.11 or later — make sure your environment is on a compatible version before upgrading.

## Removal of deprecated APIs

APIs that had been deprecated in v3 are removed in v4.

### `api_public_base_url` argument of storage clients

The deprecated `api_public_base_url` argument has been removed from the `__init__` methods of `ApifyDatasetClient` and `ApifyKeyValueStoreClient`. It had no effect already in v3 — passing it only emitted a `DeprecationWarning`. Drop it from your call sites. The public base URL is now taken from `Configuration.api_public_base_url`, which is unchanged.

### `RemainingTime` timeout literal

The deprecated `'RemainingTime'` value of the `timeout` argument has been removed from `Actor.start()` and `Actor.call()`. Use `'inherit'` instead — the behavior is identical.

Before (v3):

```python
await Actor.call('some-actor-id', timeout='RemainingTime')
```

After (v4):

```python
await Actor.call('some-actor-id', timeout='inherit')
```

### Deprecated `Configuration` fields

The following deprecated `Configuration` fields have been removed:

- `latest_sdk_version` (`APIFY_SDK_LATEST_VERSION`) — SDK version checking is not supported for the Python SDK.
- `log_format` (`APIFY_LOG_FORMAT`) — adjust the log format in code instead.
- `standby_port` (`ACTOR_STANDBY_PORT`) — use `web_server_port` instead.
