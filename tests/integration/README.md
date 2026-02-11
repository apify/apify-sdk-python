# Integration tests

These tests make real requests to the Apify API, but do not build or deploy Actors on the platform. They are faster than E2E tests and can be fully debugged locally.

When writing new tests, prefer this level if possible. Only write E2E tests (see [`tests/e2e/`](../e2e/)) when you need to test something that requires building and running an Actor on the platform.

## Running

```bash
export APIFY_TEST_USER_API_TOKEN=<your-token>
uv run poe integration-tests
```

To run against a different environment, also set `APIFY_INTEGRATION_TESTS_API_URL`.

## Key fixtures

- **`apify_client_async`** — A session-scoped `ApifyClientAsync` instance configured with the test token and API URL.
- **`prepare_test_env`** / **`_isolate_test_environment`** (autouse) — Resets global state and sets `APIFY_LOCAL_STORAGE_DIR` to a temporary directory before each test.
