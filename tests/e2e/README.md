# E2E tests

These tests build and run Actors using the Python SDK on the Apify platform. They are slower than integration tests (see [`tests/integration/`](../integration/)) because they need to build and deploy Actors.

When writing new tests, prefer integration tests if possible. Only write E2E tests when you need to test something that requires building and running an Actor on the platform.

## Running

```bash
export APIFY_TEST_USER_API_TOKEN=<your-token>
uv run poe e2e-tests
```

To run against a different environment, also set `APIFY_INTEGRATION_TESTS_API_URL`.

## Key fixtures

- **`apify_client_async`** — A session-scoped `ApifyClientAsync` instance configured with the test token and API URL.
- **`prepare_test_env`** / **`_isolate_test_environment`** (autouse) — Resets global state and sets `APIFY_LOCAL_STORAGE_DIR` to a temporary directory before each test.
- **`make_actor`** — Factory for creating temporary Actors on the Apify platform (built, then auto-deleted after the test).
- **`run_actor`** — Starts an Actor run and waits for completion (10 min timeout).

## How to write tests

### Creating an Actor from a Python function

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

The `src/main.py` file will be set to the function definition, prepended with `import asyncio` and `from apify import Actor`. You can add extra imports directly inside the function body.

### Creating an Actor from source files

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

### Assertions inside Actors

Since test Actors are not executed as standard pytest tests, we don't get introspection of assertion expressions. In case of failure, only a bare `AssertionError` is shown. Always include explicit assertion messages:

```python
assert is_finished is False, f'is_finished={is_finished}'
```
