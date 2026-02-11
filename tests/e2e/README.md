# E2E tests

These tests build and run Actors using the Python SDK on the Apify platform. They are slower than integration tests (see `tests/integration/`) because they need to build and deploy Actors. Preferably try to write integration tests first, and only write E2E tests when you need to test something that can only be tested on the platform.

## Running

```bash
# Set the API token
export APIFY_TEST_USER_API_TOKEN=<your-token>

# Run the tests
uv run poe e2e-tests
```

If you want to run the tests on a different environment than the main Apify platform, set the `APIFY_INTEGRATION_TESTS_API_URL` environment variable to the right URL.

## How to write tests

There are two fixtures which you can use to write tests:

### `apify_client_async`

This fixture just gives you an instance of `ApifyClientAsync` configured with the right token and API URL, so you don't have to do that yourself.

```python
async def test_something(apify_client_async: ApifyClientAsync) -> None:
    assert await apify_client_async.user('me').get() is not None
```

### `make_actor`

This fixture returns a factory function for creating Actors on the Apify platform.

For the Actor source, the fixture takes the files from `tests/e2e/actor_source_base`, builds the Apify SDK wheel from the current codebase, and adds the Actor source you passed to the fixture as an argument. You have to pass exactly one of the `main_func`, `main_py` and `source_files` arguments.

The created Actor will be uploaded to the platform, built there, and after the test finishes, it will be automatically deleted. If the Actor build fails, it will not be deleted, so that you can check why the build failed.

### Creating test Actor straight from a Python function

You can create Actors straight from a Python function. This is great because you can have the test Actor source code checked with the linter.

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

These Actors will have the `src/main.py` file set to the `main` function definition, prepended with `import asyncio` and `from apify import Actor`, for your convenience.

### Creating Actor from source files

You can also pass the source files directly if you need something more complex (e.g. pass some fixed value to the Actor source code or use multiple source files).

To pass the source code of the `src/main.py` file directly, use the `main_py` argument to `make_actor`:

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
                print('Hello! It is ' + datetime.now().time())
                await Actor.set_value('OUTPUT', '{expected_output}')
    """

    actor = await make_actor(label='something', main_py=main_py_source)
    await run_actor(actor)

    output_record = await actor.last_run().key_value_store().get_record('OUTPUT')
    assert output_record is not None
    assert output_record['value'] == expected_output
```

### Asserts

Since test Actors are not executed as standard pytest tests, we don't get introspection of assertion expressions. In case of failure, only a bare `AssertionError` is shown, without the left and right values. This means, we must include explicit assertion messages to aid potential debugging.

```python
async def test_add_and_fetch_requests(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test basic functionality of adding and fetching requests."""

    async def main() -> None:
        async with Actor:
            rq = await Actor.open_request_queue()
            await rq.add_request(f'https://apify.com/')
            assert is_finished is False, f'is_finished={is_finished}'

    actor = await make_actor(label='rq-test', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'
```
