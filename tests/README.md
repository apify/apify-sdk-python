# Tests

The tests have three levels:

- [Unit tests](#unit-tests) (`tests/unit`) mock the Apify API and need no credentials.
- [Integration tests](#integration-tests) (`tests/integration`) call the real Apify API without deploying Actors.
- [E2E tests](#e2e-tests) (`tests/e2e`) build and run Actors on the Apify platform.

Use the lowest level that can test what you need. Integration tests run faster than E2E tests and you can debug them locally, so write an E2E test only when the test needs an Actor built and running on the platform.

## Fixtures shared by several levels

- `prepare_test_env` and its autouse wrapper `_isolate_test_environment` (all levels): reset the global state (Actor initialization, service locator, storages) and point `APIFY_LOCAL_STORAGE_DIR` to a temporary directory before each test.
- `apify_client_async` (integration and E2E): a session-scoped `ApifyClientAsync` configured with the test token and API URL.

## Unit tests

Unit tests check the SDK's logic in isolation. They mock every external dependency, such as the Apify API and other platform services, so they're fast and need no environment variables or credentials.

### Running unit tests

```bash
uv run poe unit-tests
```

### Unit test fixtures

- `apify_client_async_patcher`: patches `ApifyClientAsync` methods to return fixed values or call replacement functions, and records the calls.
- `httpserver`: a local HTTP server (from `pytest-httpserver`) for testing HTTP interactions without real network calls.

### Troubleshooting

If a test fails with `SystemExit: 0` raised from `_actor.py` when `async with Actor:` exits, the virtual environment is missing the optional extras. Without Scrapy installed, the Actor exits the process on teardown. Run `uv sync --all-extras` or `uv run poe install-dev`.

## Integration tests

Integration tests make real requests to the Apify API, but they don't build or deploy Actors.

### Running integration tests

```bash
export APIFY_TEST_USER_API_TOKEN=<your-token>
uv run poe integration-tests
```

To run them against a different environment, also set `APIFY_INTEGRATION_TESTS_API_URL`.

### Integration test files

| File | What it tests |
| --- | --- |
| `test_dataset.py` | Dataset operations |
| `test_key_value_store.py` | Key-value store operations |
| `test_request_queue.py` | Request queue operations |
| `test_storages.py` | Behavior across storages: aliases, unnamed default storages, explicit initialization |

### Integration test fixtures

- `request_queue_apify`: creates an Apify request queue on the platform, once for each access mode (`single` and `shared`), and drops it after the test.

### Platform behavior to account for

- Right after you add a request to a shared RQ, its head can still come back empty. Poll negative assertions, such as `is_finished()`, the same way as positive ones.
- In the response of `update_request`, `wasAlreadyHandled` describes the request's state before the update.
- RQ metadata counts (`handledRequestCount`, `pendingRequestCount`) lag a few seconds behind the operations that change them.

## E2E tests

E2E tests build Actors that use the SDK and run them on the Apify platform. Building and deploying the Actors makes them the slowest level.

### Running E2E tests

```bash
export APIFY_TEST_USER_API_TOKEN=<your-token>
uv run poe e2e-tests
```

To run them against a different environment, also set `APIFY_INTEGRATION_TESTS_API_URL`.

### E2E test fixtures

- `make_actor`: creates a temporary Actor on the platform and builds it, retrying a failed build once. The Actor is deleted after the test.
- `run_actor`: starts an Actor run and waits up to 10 minutes for it to finish.

### How test Actors are built

Each test Actor gets the files from `tests/e2e/actor_source_base`, plus a wheel of the SDK built from the current code. The Dockerfile installs the wheel and the other dependencies from `requirements.txt` and runs the `src` package. The test fixture sets the base image to the Python version of the test run.

### Writing E2E tests

#### Creating an Actor from a Python function

You can create an Actor straight from a Python function, which means the linter also checks the Actor's code.

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

`make_actor` writes the function to `src/main.py`, after `import asyncio` and `from apify import Actor`. Put any other imports inside the function body.

#### Creating an Actor from source files

For a single-file Actor, pass its code as `main_py`:

```python
async def test_something(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    expected_output = f'ACTOR_OUTPUT_{crypto_random_object_id(5)}'
    main_py_source = f"""
        import asyncio
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

For an Actor with several files, pass `source_files`:

```python
actor_source_files = {
    'src/utils.py': """
        from datetime import datetime, timezone
        def get_current_datetime():
            return datetime.now(timezone.utc)
    """,
    'src/main.py': """
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

Test Actors don't run under pytest, so a failed assertion inside one shows only a bare `AssertionError`, without the values involved. Always give the assertion a message:

```python
assert is_finished is False, f'is_finished={is_finished}'
```
