# Integration tests

There are two different groups of integration tests in this repository:
- Apify API integration tests. These test that the Apify SDK is correctly communicating with Apify API through Apify client.
- Actor integration tests. These test that the Apify SDK can be used in Actors deployed to Apify platform. These are very high level tests, and they test communication with the API and correct interaction with the Apify platform.

To run these tests, you need to set the `APIFY_TEST_USER_API_TOKEN` environment variable to the API token of the Apify user you want to use for the tests, and then start them with `make integration-tests`.

## Apify API integration tests
The tests are making real requests to the Apify API as opposed to the unit tests that are mocking such API calls. On the other hand they are faster than `Actor integration tests` as they do not require building and deploying the Actor. These test can be also fully debugged locally. Preferably try to write integration tests on this level if possible.


## Actor integration tests
We have integration tests which build and run Actors using the Python SDK on the Apify platform. These integration tests are slower than `Apify API integration tests` as they need to build and deploy Actors on the platform. Preferably try to write `Apify API integration tests` first, and only write `Actor integration tests` when you need to test something that can only be tested on the platform.

If you want to run the integration tests on a different environment than the main Apify platform, you need to set the `APIFY_INTEGRATION_TESTS_API_URL` environment variable to the right URL to the Apify API you want to use.

### How to write tests

There are two fixtures which you can use to write tests:

#### `apify_client_async`

This fixture just gives you an instance of `ApifyClientAsync` configured with the right token and API URL, so you don't have to do that yourself.

```python
async def test_something(apify_client_async: ApifyClientAsync) -> None:
    assert await apify_client_async.user('me').get() is not None
```

#### `make_actor`

This fixture returns a factory function for creating Actors on the Apify platform.

For the Actor source, the fixture takes the files from `tests/integration/actor_source_base`, builds the Apify SDK wheel from the current codebase, and adds the Actor source you passed to the fixture as an argument. You have to pass exactly one of the `main_func`, `main_py` and `source_files` arguments.

The created Actor will be uploaded to the platform, built there, and after the test finishes, it will be automatically deleted. If the Actor build fails, it will not be deleted, so that you can check why the build failed.

#### Creating test Actor straight from a Python function

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

You can also pass extra imports directly to the main function:

```python
async def test_something(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main():
        import os
        from apify_shared.consts import ActorEventTypes, ActorEnvVars
        async with Actor:
            print('The Actor is running with ' + os.getenv(ActorEnvVars.MEMORY_MBYTES) + 'MB of memory')
            await Actor.on(ActorEventTypes.SYSTEM_INFO, lambda event_data: print(event_data))

    actor = await make_actor(label='something', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'
```

#### Creating Actor from source files

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

Or you can pass multiple source files with the `source_files` argument, if you need something really complex:

```python
async def test_something(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
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
                    current_datetime = get_current_datetime()
                    print('Hello! It is ' + current_datetime.time())
        """,
    }
    actor = await make_actor(label='something', source_files=actor_source_files)
    actor_run = await run_actor(actor)

    assert actor_run.status == 'SUCCEEDED'
```

#### Asserts

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
