# Integration tests

These tests make real requests to the Apify API, but do not build or deploy Actors on the platform. They are faster than E2E tests and can be fully debugged locally.

When writing new tests, prefer this level if possible. Only write E2E tests (see [`tests/e2e/`](../e2e/)) when you need to test something that requires building and running an Actor on the platform.

## Running

```bash
export APIFY_TEST_USER_API_TOKEN=<your-token>
uv run poe integration-tests
```

To run against a different environment, also set `APIFY_INTEGRATION_TESTS_API_URL`.

## Structure

| File | Description |
| --- | --- |
| `test_dataset.py` | Dataset operations |
| `test_key_value_store.py` | Key-value store operations |
| `test_request_queue.py` | Request queue operations |
| `test_storages.py` | Cross-storage tests (aliases, unnamed defaults, explicit init) |

## Key fixtures

- **`apify_client_async`** — A session-scoped `ApifyClientAsync` instance configured with the test token and API URL.
- **`request_queue_apify`** — Creates a parametrized (`single`/`shared` access mode) Apify request queue on the platform, yields it, and drops it after the test. Defined in `conftest.py`.
- **`prepare_test_env`** / **`_isolate_test_environment`** (autouse) — Resets global state and sets `APIFY_LOCAL_STORAGE_DIR` to a temporary directory before each test.
