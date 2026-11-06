# Tests

The tests are split into three levels:

- [Unit tests](#unit-tests) (`tests/unit`) mock the Apify API and need no credentials.
- [Integration tests](#integration-tests) (`tests/integration`) call the real Apify API without deploying Actors.
- [E2E tests](#e2e-tests) (`tests/e2e`) build and run Actors on the Apify platform.

Prefer the lowest level that can test what you need. Integration tests are faster than E2E tests and can be fully debugged locally, so write E2E tests only when the test needs an Actor built and running on the platform.

## Fixtures in more than one level

- **`prepare_test_env`** / **`_isolate_test_environment`** (autouse, all levels) — Resets global state (Actor initialization, service locator, storage) and sets `APIFY_LOCAL_STORAGE_DIR` to a temporary directory before each test.
- **`apify_client_async`** (integration and E2E) — A session-scoped `ApifyClientAsync` instance configured with the test token and API URL.

## Unit tests

These tests verify the SDK's internal logic in isolation, without making any real API calls. All external dependencies (Apify API, platform services) are mocked. They are fast and can be run without any environment variables or credentials.

### Running unit tests

```bash
uv run poe unit-tests
```

### Unit test fixtures

- **`apify_client_async_patcher`** — Helper for patching `ApifyClientAsync` methods to return fixed values or replacement functions, with automatic call tracking.
- **`httpserver`** — Local HTTP server (via `pytest-httpserver`) for testing HTTP interactions without real network calls.

### Troubleshooting

If tests fail with `SystemExit: 0` raised from `_actor.py` when `async with Actor:` exits, the virtual environment lacks the optional extras. Without Scrapy installed, the Actor exits the process on teardown. Run `uv sync --all-extras` (or `uv run poe install-dev`).

## Integration tests

These tests make real requests to the Apify API, but do not build or deploy Actors on the platform.

### Running integration tests

```bash
export APIFY_TEST_USER_API_TOKEN=<your-token>
uv run poe integration-tests
```

To run against a different environment, also set `APIFY_INTEGRATION_TESTS_API_URL`.

### Structure

| File | Description |
| --- | --- |
| `test_dataset.py` | Dataset operations |
| `test_key_value_store.py` | Key-value store operations |
| `test_request_queue.py` | Request queue operations |
| `test_storages.py` | Cross-storage tests (aliases, unnamed defaults, explicit init) |

### Integration test fixtures

- **`request_queue_apify`** — Creates a parametrized (`single`/`shared` access mode) Apify request queue on the platform, yields it, and drops it after the test. Defined in `conftest.py`.

### Platform behavior to account for

- Right after a request is added to a shared RQ, the head can still come back empty. Poll negative assertions (such as `is_finished()`) as well as positive ones.
- In the response of `update_request`, `wasAlreadyHandled` reflects the request's state before the update.
- RQ metadata counts (`handledRequestCount`, `pendingRequestCount`) lag a few seconds behind the operations that change them.

## E2E tests

These tests build and run Actors using the Python SDK on the Apify platform. They are slower than integration tests because they need to build and deploy Actors.

### Running E2E tests

```bash
export APIFY_TEST_USER_API_TOKEN=<your-token>
uv run poe e2e-tests
```

To run against a different environment, also set `APIFY_INTEGRATION_TESTS_API_URL`.

### E2E test fixtures

- **`make_actor`** — Factory for creating temporary Actors on the Apify platform (built, then auto-deleted after the test).
- **`run_actor`** — Starts an Actor run and waits for completion (10 min timeout).

### How test Actors are built

Every test Actor gets the files from `tests/e2e/actor_source_base` and the SDK source code under `sdk/`. Its image builds in two stages (see `tests/e2e/actor_source_base/Dockerfile`):

- The builder stage installs the SDK from `sdk/` with uv, together with the dependencies, all pinned to the project's `uv.lock`.
- The runner stage copies the resulting virtual environment and the Actor source code, and runs the `actor` package.

The Python version of the test run reaches the build as the `PYTHON_VERSION` build argument.

### How to write tests

#### Creating an Actor from a Python function

You can create Actors straight from a Python function. This is great because the test Actor source code gets checked by the linter.

```python
async def test_something(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        async with Actor:
            print('Hello!')

    actor = await make_actor(label='something', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'
```

The `actor/main.py` file will be set to the function definition, prepended with `import asyncio` and `from apify import Actor`. You can add extra imports directly inside the function body.

#### Creating an Actor from source files

Pass the `main_py` argument for a single-file Actor:

```python
async def test_something(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    expected_output = f'ACTOR_OUTPUT_{crypto_random_object_id(5)}'
    main_py_source = f"""
        import asyncio
        from datetime import datetime
        from apify import Actor
        async def main():
            async with Actor:
                await Actor.set_value('OUTPUT', '{expected_output}')
    """

    actor = await make_actor(label='something', main_py=main_py_source)
    await run_actor(actor)

    output_record = await actor.last_run().key_value_store().get_record('OUTPUT')
    assert output_record is not None
    assert output_record['value'] == expected_output
```

Or pass `source_files` for multi-file Actors:

```python
actor_source_files = {
    'actor/utils.py': """
        from datetime import datetime, timezone
        def get_current_datetime():
            return datetime.now(timezone.utc)
    """,
    'actor/main.py': """
        import asyncio
        from apify import Actor
        from .utils import get_current_datetime
        async def main():
            async with Actor:
                print('Hello! It is ' + str(get_current_datetime()))
    """,
}
actor = await make_actor(label='something', source_files=actor_source_files)
```

#### Assertions inside Actors

Since test Actors are not executed as standard pytest tests, we don't get introspection of assertion expressions. In case of failure, only a bare `AssertionError` is shown. Always include explicit assertion messages:

```python
assert is_finished is False, f'is_finished={is_finished}'
```
