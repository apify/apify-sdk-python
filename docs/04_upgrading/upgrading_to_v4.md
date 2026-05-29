---
id: upgrading-to-v4
title: Upgrading to v4
description: Breaking changes and migration guide from Apify SDK v3.x to v4.0.
---

This guide lists the breaking changes between Apify Python SDK v3.x and v4.0.

## Python 3.11+ required

Support for Python 3.10 has been dropped. The Apify Python SDK v4.x now requires Python 3.11 or later — make sure your environment is on a compatible version before upgrading.

## Keyword-only arguments for secondary parameters

Several `Actor` methods had a `*` separator inserted into their signatures, so optional/secondary parameters can no longer be passed positionally. The "subject" arguments (e.g. `key` on `get_value`, `data` on `push_data`, `event_name` on `charge`) remain positional; only the parameters that follow them are affected.

### Affected APIs

- `Actor.get_value(key, *, default_value=None)`
- `Actor.push_data(data, *, charged_event_name=None)`
- `Actor.charge(event_name, *, count=1)`
- `Actor.use_state(default_value=None, *, key=None, kvs_name=None)`

The same treatment was applied to the `ChargingManager.charge(event_name, *, count=1)` method returned by `Actor.get_charging_manager()`.

### Migration

Before (v3):

```python
value = await Actor.get_value('my-key', default_value)
await Actor.push_data(data, 'my-event')
await Actor.charge('my-event', 5)
```

After (v4):

```python
value = await Actor.get_value('my-key', default_value=default_value)
await Actor.push_data(data, charged_event_name='my-event')
await Actor.charge('my-event', count=5)
```
