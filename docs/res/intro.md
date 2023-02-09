# Apify SDK for Python

`apify` is the official library to create [Apify Actors] in Python.
It provides useful features like automatic retries and convenience functions that improve the experience of using the Apify API.

* [Quick Start](#quick-start)
  * [Developing Python actors locally](#developing-python-actors-locally)
* [Features](#features)
  * [Local storage emulation](#local-storage-emulation)
  * [Automatic configuration](#automatic-configuration)
  * [Interacting with other actors](#interacting-with-other-actors)
* [Usage concepts](#usage-concepts)
  * [Actor lifecycle](#actor-lifecycle)
  * [Working with storages](#working-with-storages)
  * [Working with proxies](#working-with-proxies)
  * [Direct access to the Apify API](#direct-access-to-the-apify-api)
  * [Managing actor events](#managing-actor-events)
* [API Reference](#api-reference)

## Installation

Requires Python 3.8+

You can install the Apify SDK from its [PyPI listing](https://pypi.org/project/apify/).
To do that, simply run `pip install apify`.

## Quick Start

```python
import asyncio
from apify import Actor

async def main():
    async with Actor() as actor:
        actor_input = await actor.get_input()
        print('Actor input:', actor_input)

        await actor.push_data([
            {'id': 1, 'result': 'first_result'},
            {'id': 2, 'result': 'second_result'}
        ])

        await actor.set_value('OUTPUT', 'Hello, world!')

asyncio.run(main())
```

### Developing Python actors locally

```bash
apify create my-python-actor --template python-sdk
cd my-python-actor
apify run
```

## Features

### Local storage emulation

When running actors locally, the Apify SDK performs storage operations like `Actor.push_data()` or `Actor.set_value()` on the local filesystem, in the `storage` folder in the actor project directory.

### Automatic configuration

When running actors on the Apify Platform, the SDK automatically configures the actor using the environment variables the platform provides to the actor's container. This means you don't have to specify your Apify API token, your Apify Proxy password, or the default storage IDs manually, everything is configured right from the start.

### Interacting with other actors

You can interact with other actors with some useful API wrappers.
`Actor.start(other_actor_id, run_input=...)` starts a run of another actor, `Actor.call(other_actor_id, run_input=...)` starts a run of another actor and waits for it to finish, and `Actor.call_task(actor_task_id)` starts a run of an actor task and waits for it to finish.

## Usage concepts

### Actor lifecycle

At the start its runtime, the actor needs to initialize itself, its event manager and its storages, and at the end of the runtime it needs to deinitialize these cleanly. The Apify SDK provides several options on how to manage this.

#### `Actor.init()` and `Actor.exit()`

The `Actor.init()` method initializes the actor, the event manager which processes the actor events from the event websocket, and the storage client used in the execution environment. It should be called before performing any actor operations.

The `Actor.exit()` method then exits the actor cleanly, tearing down the event manager and the storage client. There is also the `Actor.fail()` method, which exits the actor while marking it as failed.

```python
import asyncio
from apify import Actor
from apify.consts import ActorExitCodes

async def main():
    await Actor.init()
    try:
        print('Actor input:', await Actor.get_input())
        await Actor.set_value('OUTPUT', 'Hello, world!')
        await Actor.exit()
        raise RuntimeError('Ouch!')
    except Exception as e:
        print('Error while running actor', e)
        await Actor.fail(exit_code=ActorExitCodes.ERROR_USER_FUNCTION_THREW, exception=e)

asyncio.run(main())
```

#### Context manager

So that you don't have to call the lifecycle methods manually, the `Actor` class provides a context manager, which calls the `Actor.init()` method on enter, the `Actor.exit()` method on a clean exit, and the `Actor.fail()` method when there is an exception during the run of the actor.

This is the recommended way to work with the `Actor` class.

```python
import asyncio
from apify import Actor

async def main():
    async with Actor:
        print('Actor input:', await Actor.get_input())
        await Actor.set_value('OUTPUT', 'Hello, world!')
        raise RuntimeError('Ouch!')

asyncio.run(main())
```

#### Main function

Another option is to pass a function to the actor via the `Actor.main(main_func)`, which causes the actor to initialize, run the main function, and exit, catching any runtime errors in the passed function.

```python
import asyncio
from apify import Actor

async def actor_main_func():
    print('Actor input:', await Actor.get_input())
    await Actor.set_value('OUTPUT', 'Hello, world!')
    raise RuntimeError('Ouch!')

async def main():
    await Actor.main(actor_main_func)

asyncio.run(main())
```

### Working with storages

The `Actor` class provides methods to work either with the default storages of the actor, or with any other storage, named or unnamed.

#### Convenience methods for default storages

There are several methods for directly working with the default key-value store or default dataset of the actor.

`Actor.get_value('my-record')` reads a record from the default key-value store of the actor.

`Actor.set_value('my-record', 'my-value')` saves a new value to the record in the default key-value store.

`Actor.get_input()` reads the actor input from the default key-value store of the actor.

`Actor.push_data([{'result': 'Hello, world!'}, ...])` saves results to the default dataset of the actor.

#### Opening other storages

The `Actor.open_dataset()`, `Actor.open_key_value_store()` and `Actor.open_request_queue()` methods can be used to open any storage for reading and writing. You can either use them without arguments to open the default storages, or you can pass a storage ID or name to open another storage.

```python
import asyncio
from apify import Actor

async def main():
    async with Actor:
        # Work with the default dataset of the actor
        dataset = await Actor.open_dataset()
        await dataset.push_data({'result': 'Hello, world!'})

        # Work with the key-value store with ID 'mIJVZsRQrDQf4rUAf'
        key_value_store = await Actor.open_key_value_store(id='mIJVZsRQrDQf4rUAf')
        await key_value_store.set_value('record', 'Hello, world!')

        # Work with the request queue with name 'my-queue'
        request_queue = await Actor.open_request_queue(name='my-queue')
        await request_queue.add_request({ 'uniqueKey': 'v0Ngr', 'url': 'https://example.com' })

asyncio.run(main())
```

### Working with proxies

To work with proxies in your actor, you can use the `Actor.create_proxy_configuration()` method, which allows you to generate proxy URLs either for the Apify Proxy, or even for your own proxies, with automatic proxy rotation and support for sessions.

```python
import asyncio
import httpx
from apify import Actor

async def main():
    async with Actor:
        # You can either set the proxy config manually
        proxy_configuration = await Actor.create_proxy_configuration(groups=['RESIDENTIAL'], country_code='US')

        # --- OR ---
        # You can get the proxy config from the actor input, if it has such input in its input schema
        actor_input = await Actor.get_input()
        selected_proxy_config = actor_input['proxyConfiguration']
        proxy_configuration = await Actor.create_proxy_configuration(actor_proxy_input=selected_proxy_config)

        # --- OR ---
        # You can use your own proxy servers
        proxy_configuration = await Actor.create_proxy_configuration(proxy_urls=['http://my-proxy.com:8000', 'http://my-other-proxy.com:8000'])

        proxy_url = await proxy_configuration.new_url(session_id='uj96X')

        async with httpx.AsyncClient(proxies=proxy_url) as httpx_client:
            response = await client.get('http://example.com')
            await Actor.set_value('OUTPUT', response.text

asyncio.run(main())
```

### Direct access to the Apify API

If you need to access the Apify API directly, you can use the pre-configured Apify API client, available in the `Actor.apify_client` property, without having to set the API token manually.

```python
import asyncio
from apify import Actor

async def main():
    async with Actor:
        client = Actor.apify_client
        me = await client.user('me').get()
        print(me)

asyncio.run(main())
```

### Managing actor events

The Apify Platform sends several events to the actor. If you want to work with them, you can use the `Actor.on()` and `Actor.off()` methods:

```python
import asyncio
from pprint import pprint
from apify import Actor
from apify.consts import ActorEventTypes

async def print_system_info(event_data):
    print('Actor system info from platform:')
    pprint(event_data)

async def react_to_abort(event_data):
    print('The actor is aborting!')
    pprint(event_data)

async def persist_state(event_data):
    print('The actor should persist its state!')
    pprint(event_data)
    # Add your state persisting logic here

async def main():
    async with Actor:
        Actor.on(ActorEventTypes.SYSTEM_INFO, print_system_info)
        Actor.on(ActorEventTypes.ABORTING, react_to_abort)
        Actor.on(ActorEventTypes.PERSIST_STATE, persist_state)

        # Do some work here
        ...

        # We are no longer interested in the system info, we can remove the event handler
        Actor.off(ActorEventTypes.SYSTEM_INFO, print_system_info)

        # Do some more work here
        ...

asyncio.run(main())
```
