Integration tests
=================

We have integration tests which build and run actors using the Python SDK on the Apify Platform.
To run these tests, you need to set the `APIFY_TEST_USER_API_TOKEN` environment variable to the API token of the Apify user you want to use for the tests,
and then start them with `make integration-tests`.

If you want to run the integration tests on a different environment than the main Apify Platform,
you need to set the `APIFY_INTEGRATION_TESTS_API_URL` environment variable to the right URL to the Apify API you want to use.

How to write tests
------------------

There are two fixtures which you can use to write tests:

### `apify_client_async`

This fixture just gives you an instance of `ApifyClientAsync` configured with the right token and API URL,
so you don't have to do that yourself.

```python
async def test_something(apify_client_async: ApifyClientAsync) -> None:
    assert await apify_client_async.user('me').get() is not None
```

### `make_actor`

This fixture returns a factory function for creating actors on the Apify Platform.

For the actor source, the fixture takes the files from `tests/integration/actor_source_base`,
builds the Apify SDK wheel from the current codebase,
and adds the actor source you passed to the fixture as an argument.

The created actor will be uploaded to the platform, built there, and after the test finishes, it will be automatically deleted.
If the actor build fails, it will not be deleted, so that you can check why the build failed.

You can create actors straight from a Python function:

```python
async def test_something(self, make_actor: ActorFactory) -> None:
    async def main() -> None:
        async with Actor:
            print('Hello!')

    actor = await make_actor('something', main_func=main)

    run_result = await actor.call()

    assert run_result is not None
    assert run_result['status'] == 'SUCCEEDED'
```

Or you can pass the `src/main.py` file, if you need something more complex
(e.g. specify more imports or pass some fixed value to the actor source code):

```python
async def test_something(self, make_actor: ActorFactory) -> None:
    expected_output = f'ACTOR_OUTPUT_{_crypto_random_object_id(5)}'
    main_py_source = f"""
        import asyncio
        from datetime import datetime
        from apify import Actor
        async def main():
            async with Actor:
                print('Hello! It is ' + datetime.now().time())
                await Actor.set_value('OUTPUT', '{expected_output}')
    """

    actor = await make_actor('something', main_py=main_py_source)

    await actor.call()

    output_record = await actor.last_run().key_value_store().get_record('OUTPUT')
    assert output_record is not None
    assert output_record['value'] == expected_output

```

Or you can pass multiple source files, if you need something really complex:

```python
async def test_something(self, make_actor: ActorFactory) -> None:
    actor_source_files = {
        'src/utils.py': """
            from datetime import datetime

            def get_current_datetime():
                return datetime.utcnow()
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
    actor = await make_actor('something', source_files=actor_source_files)

    actor_run = await actor.call()
    assert actor_run is not None
    assert actor_run['status'] == 'SUCCEEDED'
```

You have to pass exactly one of the `main_func`, `main_py` and `source_files` arguments.
