---
id: upgrading-to-v4
title: Upgrading to v4
description: Breaking changes and migration guide from Apify SDK v3.x to v4.0.
---

This guide lists the breaking changes between Apify Python SDK v3.x and v4.0.

## Python 3.11+ required

Support for Python 3.10 has been dropped. The Apify Python SDK v4.x now requires Python 3.11 or later — make sure your environment is on a compatible version before upgrading.

## Keyword-only arguments

Secondary parameters on these methods can no longer be passed positionally.

```python
# Before
value = await Actor.get_value('my-key', default_value)
await Actor.push_data(data, 'my-event')
await Actor.charge('my-event', 5)

# After
value = await Actor.get_value('my-key', default_value=default_value)
await Actor.push_data(data, charged_event_name='my-event')
await Actor.charge('my-event', count=5)
```

Affected signatures:

- `Actor` — `get_value`, `push_data`, `charge`, `use_state`.
- `ChargingManager` — `charge`.
