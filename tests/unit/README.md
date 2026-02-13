# Unit tests

These tests verify the SDK's internal logic in isolation, without making any real API calls. All external dependencies (Apify API, platform services) are mocked. They are fast and can be run without any environment variables or credentials.

## Running

```bash
uv run poe unit-tests
```

## Key fixtures

- **`prepare_test_env`** / **`_isolate_test_environment`** (autouse) — Resets global state (Actor initialization, service locator, storage) and sets `APIFY_LOCAL_STORAGE_DIR` to a temporary directory before each test.
- **`apify_client_async_patcher`** — Helper for patching `ApifyClientAsync` methods to return fixed values or replacement functions, with automatic call tracking.
- **`httpserver`** — Local HTTP server (via `pytest-httpserver`) for testing HTTP interactions without real network calls.
