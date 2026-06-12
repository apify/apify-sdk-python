---
id: upgrading-to-v4
title: Upgrading to v4
description: Breaking changes and migration guide from Apify SDK v3.x to v4.0.
---

This guide lists the breaking changes between Apify Python SDK v3.x and v4.0.

## Python version support

Support for Python 3.10 has been dropped. The Apify Python SDK v4.x now requires Python 3.11 or later — make sure your environment is on a compatible version before upgrading.

## Keyword-only arguments

Secondary parameters in these signatures can no longer be passed positionally:
- `Actor` — `get_value`, `push_data`, `charge`, `use_state`.
- `ChargingManager` — `charge`.

```python
# Before (v3)
value = await Actor.get_value('my-key', default_value)
await Actor.push_data(data, 'my-event')
await Actor.charge('my-event', 5)

# After (v4)
value = await Actor.get_value('my-key', default_value=default_value)
await Actor.push_data(data, charged_event_name='my-event')
await Actor.charge('my-event', count=5)
```

## Removal of deprecated APIs

Methods and arguments that had been deprecated in v3 are removed in v4.

### api_public_base_url argument of storage clients

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

### Actor.start and Actor.call: RemainingTime

The deprecated `RemainingTime` value of the `timeout` argument has been removed from `Actor.start()` and `Actor.call()`. Use `inherit` instead, the signature and behavior are identical.

```python
# Before (v3)
run = await Actor.call('user/actor', timeout='RemainingTime')

# After (v4)
run = await Actor.call('user/actor', timeout='inherit')
```

### Deprecated Configuration fields

The deprecated `latest_sdk_version`, `log_format`, and `standby_port` fields have been removed from `Configuration`:
- In place of `standby_port`, use `web_server_port`.
- `latest_sdk_version` and `log_format` don't have replacement. SDK version checking isn't supported for the Python SDK and the log format should be adjusted in code instead.

## Built on apify-client v3

The SDK is now built on [`apify-client`](https://docs.apify.com/api/client/python) v3 and no longer depends on `apify-shared`. The sections below cover the user-visible consequences; see the client's [Upgrading to v3](https://docs.apify.com/api/client/python/docs/upgrading/upgrading-to-v3) guide for the full list of changes in the client itself.

### Environment variable enums moved

If you imported the platform environment-variable enums from `apify_shared.consts` (`ApifyEnvVars`, `ActorEnvVars`), import them from `apify` instead — they are now vendored in the SDK and re-exported from the top-level package.

```python
# Before (v3)
from apify_shared.consts import ApifyEnvVars

# After (v4)
from apify import ApifyEnvVars
```

### Typed responses

`Actor.start`, `Actor.abort`, `Actor.call`, `Actor.call_task`, and `Actor.set_status_message` now return `apify_client._models.Run` instead of the SDK-side `ActorRun`. Both are [Pydantic](https://docs.pydantic.dev/latest/) models with the same snake_case fields, so field access is unchanged — only the type and import path differ. The SDK no longer ships its own response models (`apify._models` has been removed); response shapes come from `apify-client`.

### Literal string aliases instead of StrEnum classes

Generated enum-like types are now [`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal) string aliases instead of `StrEnum` classes. Pass plain strings instead of enum members.

- `apify.WebhookEventType` is now a `Literal[...]` instead of a `StrEnum`. Use plain string values (`'ACTOR.RUN.FAILED'`) instead of enum members.
- `apify_shared.consts.ActorEventTypes` (a `StrEnum`) is replaced by `apify.ActorEventTypes`, now a `Literal['systemInfo', 'persistState', 'migrating', 'aborting']`. For runtime values, use `apify.Event` (re-exported from Crawlee) instead of enum members.

```python
# Before (v3)
from apify import Actor
from apify_shared.consts import ActorEventTypes

Actor.on(ActorEventTypes.SYSTEM_INFO, callback)

# After (v4)
from apify import Actor, Event

Actor.on(Event.SYSTEM_INFO, callback)
```

### Actor pricing info models

The Actor pricing-info models exposed through `Actor.configuration.actor_pricing_info` — `FreeActorPricingInfo`, `FlatPricePerMonthActorPricingInfo`, `PricePerDatasetItemActorPricingInfo`, `PayPerEventActorPricingInfo`, and the nested `ActorChargeEvent` / `PricingPerEvent` — are now thin subclasses of the corresponding `apify-client` models instead of standalone SDK copies. The discriminated-union shape is unchanged, so existing access (`pricing_model`, per-event titles and prices) keeps working; the models now expose the full `apify-client` field set, and a charge event's `event_price_usd` is optional (it is unset for tier-priced events). `ChargingManager.get_pricing_info()` is unchanged.

### Webhook API simplified

The `Webhook` model has been slimmed down to only the fields a user sets when defining a webhook. Server-populated response fields (`id`, `created_at`, `modified_at`, `user_id`, `is_ad_hoc`, `condition`, `last_dispatch`, `stats`) and the unused `WebhookCondition` helper class have been removed. The `description` and `should_interpolate_strings` fields have also been removed — they are not part of the ad-hoc webhook representation (`event_types`, `request_url`, `payload_template`, `headers_template`) that `Actor.start` / `Actor.call` / `Actor.call_task` and `Actor.add_webhook` now send. `Webhook` is now a plain `@dataclass` instead of a Pydantic `BaseModel` — construct it with snake_case kwargs; `.model_dump()` / `.model_validate()` are gone.

The retry and idempotency kwargs that used to live on `Actor.add_webhook` have moved onto the `Webhook` instance itself.

```python
# Before (v3)
from apify import Actor, Webhook

await Actor.add_webhook(
    Webhook(event_types=['ACTOR.RUN.FAILED'], request_url='https://example.com'),
    ignore_ssl_errors=False,
    do_not_retry=False,
    idempotency_key='my-key',
)

# After (v4)
from apify import Actor, Webhook

await Actor.add_webhook(
    Webhook(
        event_types=['ACTOR.RUN.FAILED'],
        request_url='https://example.com',
        ignore_ssl_errors=False,
        do_not_retry=False,
        idempotency_key='my-key',
    )
)
```

The `idempotency_key` kwarg form on `Actor.add_webhook` still works for one more release but emits a `DeprecationWarning` and will be removed in v5.0. The `ignore_ssl_errors` and `do_not_retry` kwargs have been removed outright — set them on the `Webhook` instance.

The SDK now binds the webhook to the current Actor run internally, so there is no webhook condition for you to set.

The `webhooks` argument on `Actor.start`, `Actor.call`, and `Actor.call_task` still accepts `list[Webhook]` and the fields used at the call site (`event_types`, `request_url`, `payload_template`, `headers_template`) are unchanged.

### Actor.new_client — timeout scales all tiers

`apify-client` v3 split its single timeout into four tiers (short / medium / long / max). `Actor.new_client(timeout=...)` still takes a single `timedelta`; the SDK uses it as the medium-tier baseline and scales the other tiers proportionally (short = `timeout / 6`, long = `timeout * 12`, max = `timeout * 12`). The public signature is unchanged — no migration needed.

## Using the client from Actor.new_client

`Actor.new_client()` (and the `Actor.apify_client` property) now returns an `apify-client` v3 `ApifyClientAsync`. When you use that client directly, the client's v3 breaking changes apply — the most impactful ones are below. See the client's [Upgrading to v3](https://docs.apify.com/api/client/python/docs/upgrading/upgrading-to-v3) guide for the complete reference.

### 404 raises NotFoundError on ambiguous endpoints

Direct `.get(id)` and `.delete(id)` calls still swallow 404 into `None`. But where a 404 could mean either the parent or the sub-resource is missing, the client now raises `NotFoundError` instead of returning `None`.

```python
# Before (v3)
client = Actor.new_client()

# Returned None on 404.
dataset = await client.run('some-run-id').dataset().get()

# After (v4)
from apify_client.errors import NotFoundError

client = Actor.new_client()

# Raises NotFoundError; handle it explicitly.
try:
    dataset = await client.run('some-run-id').dataset().get()
except NotFoundError:
    dataset = None
```

### Keyword-only arguments

Secondary parameters on several client methods can no longer be passed positionally.

```python
# Before (v3)
await client.key_value_store('my-store').set_record('my-key', {'data': 1}, 'application/json')
await client.run('my-run').charge('my-event', 5)

# After (v4)
await client.key_value_store('my-store').set_record('my-key', {'data': 1}, content_type='application/json')
await client.run('my-run').charge('my-event', count=5)
```

### Async iterate_* are no longer coroutine functions

`DatasetClientAsync.iterate_items()` and `KeyValueStoreClientAsync.iterate_keys()` are now plain `def` functions returning `AsyncIterator[T]`. Consumer code (`async for ...`) is unchanged; if you annotate the call's return value, change `AsyncGenerator[T, None]` to `AsyncIterator[T]`.

## Scrapy requests and HTTP cache stored as JSON

This applies only if you use the Scrapy integration (`apify[scrapy]`).

The integration now serializes data as JSON instead of pickle. `ApifyScheduler` stores Scrapy requests in the Apify request queue (under `user_data['scrapy_request']`), and `ApifyCacheStorage` stores HTTP cache entries in the key-value store. Both now hold JSON. Unlike pickle, JSON stays stable across Python and library versions.

### Persisted data from before the upgrade is not read back

Data written by an older SDK uses the pickle format, which v4 does not load. The two storages handle this differently:

- HTTP cache: a legacy entry is treated as a cache miss. Scrapy re-fetches the page and re-stores it as JSON, so the cache heals itself. No action is needed.
- Request queue: a request stored by an older SDK cannot be reconstructed, so it is skipped and the failure is logged. This matters only when pre-upgrade requests are still in the queue, for example after a run is migrated or restarted, or when you reuse a named request queue. A fresh run is not affected.

### meta and cb_kwargs must be JSON-serializable

Pickle could store arbitrary Python objects. JSON cannot, so the values in a request's `meta` and `cb_kwargs` are now subject to JSON's type system:

- A `tuple` comes back as a `list`.
- Non-string `dict` keys come back as strings, so `{1: 'a'}` becomes `{'1': 'a'}`.
- A value JSON cannot represent (`datetime`, `set`, `Decimal`, a custom object) is no longer stored silently. The request is skipped and the failure is logged. Pydantic models are still supported and are dumped with `model_dump()`.

Convert such values to a JSON-friendly form before yielding the request:

```python
from datetime import datetime

# Before (v3): relied on pickle to store the datetime object.
yield scrapy.Request(url, meta={'since': datetime(2024, 1, 1)})

# After (v4): store a JSON-serializable value.
yield scrapy.Request(url, meta={'since': datetime(2024, 1, 1).isoformat()})
```
