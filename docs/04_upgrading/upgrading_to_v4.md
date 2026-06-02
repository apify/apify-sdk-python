---
id: upgrading-to-v4
title: Upgrading to v4
description: Breaking changes and migration guide from Apify SDK v3.x to v4.0.
---

This guide lists the breaking changes between Apify Python SDK v3.x and v4.0.

## Python 3.11+ required

Support for Python 3.10 has been dropped. The Apify Python SDK v4.x now requires Python 3.11 or later — make sure your environment is on a compatible version before upgrading.

## Removal of deprecated APIs

Methods and arguments that had been deprecated in v3 are removed in v4.

### `api_public_base_url` argument of storage clients

The deprecated `api_public_base_url` argument has been removed from `ApifyDatasetClient` and `ApifyKeyValueStoreClient`. It had no effect already in v3, passing it emitted only a `DeprecationWarning`. Drop it from your call sites. The public base URL is taken from `Configuration.api_public_base_url`, which is unchanged.

```python
# Before (v3)
client = ApifyDatasetClient(
    api_client=api_client,
    api_public_base_url='https://api.apify.com',
    lock=lock,
)

# After (v4)
client = ApifyDatasetClient(
    api_client=api_client,
    lock=lock,
)
```

### `Actor.start` and `Actor.call`: `RemainingTime`

The deprecated `RemainingTime` value of the `timeout` argument has been removed from `Actor.start()` and `Actor.call()`. Use `inherit` instead, the signature and behavior are identical.

```python
# Before (v3)
run = await Actor.call('user/actor', timeout='RemainingTime')

# After (v4)
run = await Actor.call('user/actor', timeout='inherit')
```

### Deprecated `Configuration` fields

The deprecated `latest_sdk_version`, `log_format`, and `standby_port` fields have been removed from `Configuration`:
- In place of `standby_port`, use `web_server_port`.
- `latest_sdk_version` and `log_format` don't have replacement. SDK version checking isn't supported for the Python SDK and the log format should be adjusted in code instead.
