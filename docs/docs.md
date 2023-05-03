# Apify SDK for Python

`apify` is the official library to create [Apify Actors](https://docs.apify.com/platform/actors) in Python.
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

## API Reference

All public classes, methods and their parameters can be inspected in this API reference.

### [](#actor) Actor

The main class of the SDK, through which all the actor operations should be done.

* [\_\_init\_\_()](#actor-\_\_init\_\_)
* [async init()](#actor-init)
* [async exit()](#actor-exit)
* [async fail()](#actor-fail)
* [async main()](#actor-main)
* [new\_client()](#actor-new\_client)
* [async open\_dataset()](#actor-open\_dataset)
* [async open\_key\_value\_store()](#actor-open\_key\_value\_store)
* [async open\_request\_queue()](#actor-open\_request\_queue)
* [async push\_data()](#actor-push\_data)
* [async get\_input()](#actor-get\_input)
* [async get\_value()](#actor-get\_value)
* [async set\_value()](#actor-set\_value)
* [on()](#actor-on)
* [off()](#actor-off)
* [is\_at\_home()](#actor-is\_at\_home)
* [get\_env()](#actor-get\_env)
* [async start()](#actor-start)
* [async abort()](#actor-abort)
* [async call()](#actor-call)
* [async call\_task()](#actor-call\_task)
* [async metamorph()](#actor-metamorph)
* [async reboot()](#actor-reboot)
* [async add\_webhook()](#actor-add\_webhook)
* [async set\_status\_message()](#actor-set\_status\_message)
* [async create\_proxy\_configuration()](#actor-create\_proxy\_configuration)

***

#### [](#actor-__init__) `Actor.__init__(config=None)`

Create an Actor instance.

Note that you don’t have to do this, all the methods on this class function as classmethods too,
and that is their preferred usage.

* **Parameters**

  * **config** (`Configuration`, *optional*) – The actor configuration to be used. If not passed, a new Configuration instance will be created.

***

#### [](#actor-init) `async Actor.init()`

Initialize the actor instance.

This initializes the Actor instance.
It configures the right storage client based on whether the actor is running locally or on the Apify platform,
it initializes the event manager for processing actor events,
and starts an interval for regularly sending PERSIST_STATE events,
so that the actor can regularly persist its state in response to these events.

This method should be called immediately before performing any additional actor actions,
and it should be called only once.

* **Return type**

  `None`

***

#### [](#actor-exit) `async Actor.exit(*, exit_code=0, event_listeners_timeout_secs=5, status_message=None)`

Exit the actor instance.

This stops the Actor instance.
It cancels all the intervals for regularly sending PERSIST_STATE events,
sends a final PERSIST_STATE event,
waits for all the event listeners to finish,
and stops the event manager.

* **Parameters**

  * **exit_code** (`int`, *optional*) – The exit code with which the actor should fail (defaults to 0).

  * **event_listeners_timeout_secs** (`float`, *optional*) – How long should the actor wait for actor event listeners to finish before exiting.

  * **status_message** (`str`, *optional*) – The final status message that the actor should display.

* **Return type**

  `None`

***

#### [](#actor-fail) `async Actor.fail(*, exit_code=1, exception=None, status_message=None)`

Fail the actor instance.

This performs all the same steps as Actor.exit(),
but it additionally sets the exit code to 1 (by default).

* **Parameters**

  * **exit_code** (`int`, *optional*) – The exit code with which the actor should fail (defaults to 1).

  * **exception** (`BaseException`, *optional*) – The exception with which the actor failed.

  * **status_message** (`str`, *optional*) – The final status message that the actor should display.

* **Return type**

  `None`

***

#### [](#actor-main) `async Actor.main(main_actor_function)`

Initialize the actor, run the passed function and finish the actor cleanly.

**The \`Actor.main()\` function is optional** and is provided merely for your convenience.
It is mainly useful when you’re running your code as an actor on the [Apify platform]([https://apify.com/actors](https://apify.com/actors)).

The Actor.main() function performs the following actions:

* When running on the Apify platform (i.e. APIFY_IS_AT_HOME environment variable is set),
it sets up a connection to listen for platform events.
For example, to get a notification about an imminent migration to another server.

* It invokes the user function passed as the main_actor_function parameter.

* If the user function was an async function, it awaits it.

* If the user function throws an exception or some other error is encountered,
it prints error details to console so that they are stored to the log,
and finishes the actor cleanly.

* Finally, it exits the Python process, with zero exit code on success and non-zero on errors.

* **Parameters**

  * **main_actor_function** (`Callable`) – The user function which should be run in the actor

* **Return type**

  `Optional`[`TypeVar`(`MainReturnType`)]

***

#### [](#actor-new_client) `Actor.new_client(*, token=None, api_url=None, max_retries=None, min_delay_between_retries_millis=None, timeout_secs=None)`

Return a new instance of the Apify API client.

The ApifyClientAsync class is provided by the [apify-client]([https://github.com/apify/apify-client-python](https://github.com/apify/apify-client-python)) package,
and it is automatically configured using the APIFY_API_BASE_URL and APIFY_TOKEN environment variables.

You can override the token via the available options.
That’s useful if you want to use the client as a different Apify user than the SDK internals are using.

* **Parameters**

  * **token** (`str`, *optional*) – The Apify API token

  * **api_url** (`str`, *optional*) – The URL of the Apify API server to which to connect to. Defaults to [https://api.apify.com](https://api.apify.com)

  * **max_retries** (`int`, *optional*) – How many times to retry a failed request at most

  * **min_delay_between_retries_millis** (`int`, *optional*) – How long will the client wait between retrying requests
  (increases exponentially from this value)

  * **timeout_secs** (`int`, *optional*) – The socket timeout of the HTTP requests sent to the Apify API

* **Return type**

  `ApifyClientAsync`

***

#### [](#actor-open_dataset) `async Actor.open_dataset(*, id=None, name=None, force_cloud=False)`

Open a dataset.

Datasets are used to store structured data where each object stored has the same attributes,
such as online store products or real estate offers.
The actual data is stored either on the local filesystem or in the Apify cloud.

* **Parameters**

  * **id** (`str`, *optional*) – ID of the dataset to be opened.
  If neither id nor name are provided, the method returns the default dataset associated with the actor run.

  * **name** (`str`, *optional*) – Name of the dataset to be opened.
  If neither id nor name are provided, the method returns the default dataset associated with the actor run.

  * **force_cloud** (`bool`, *optional*) – If set to True then the Apify cloud storage is always used.
  This way it is possible to combine local and cloud storage.

* **Returns**

  An instance of the Dataset class for the given ID or name.

* **Return type**

  `Dataset`

***

#### [](#actor-open_key_value_store) `async Actor.open_key_value_store(*, id=None, name=None, force_cloud=False)`

Open a key-value store.

Key-value stores are used to store records or files, along with their MIME content type.
The records are stored and retrieved using a unique key.
The actual data is stored either on a local filesystem or in the Apify cloud.

* **Parameters**

  * **id** (`str`, *optional*) – ID of the key-value store to be opened.
  If neither id nor name are provided, the method returns the default key-value store associated with the actor run.

  * **name** (`str`, *optional*) – Name of the key-value store to be opened.
  If neither id nor name are provided, the method returns the default key-value store associated with the actor run.

  * **force_cloud** (`bool`, *optional*) – If set to True then the Apify cloud storage is always used.
  This way it is possible to combine local and cloud storage.

* **Returns**

  An instance of the KeyValueStore class for the given ID or name.

* **Return type**

  `KeyValueStore`

***

#### [](#actor-open_request_queue) `async Actor.open_request_queue(*, id=None, name=None, force_cloud=False)`

Open a request queue.

Request queue represents a queue of URLs to crawl, which is stored either on local filesystem or in the Apify cloud.
The queue is used for deep crawling of websites, where you start with several URLs and then
recursively follow links to other pages. The data structure supports both breadth-first
and depth-first crawling orders.

* **Parameters**

  * **id** (`str`, *optional*) – ID of the request queue to be opened.
  If neither id nor name are provided, the method returns the default request queue associated with the actor run.

  * **name** (`str`, *optional*) – Name of the request queue to be opened.
  If neither id nor name are provided, the method returns the default request queue associated with the actor run.

  * **force_cloud** (`bool`, *optional*) – If set to True then the Apify cloud storage is always used.
  This way it is possible to combine local and cloud storage.

* **Returns**

  An instance of the RequestQueue class for the given ID or name.

* **Return type**

  `RequestQueue`

***

#### [](#actor-push_data) `async Actor.push_data(data)`

Store an object or a list of objects to the default dataset of the current actor run.

* **Parameters**

  * **data** (`object or list of objects`, *optional*) – The data to push to the default dataset.

* **Return type**

  `None`

***

#### [](#actor-get_input) `async Actor.get_input()`

Get the actor input value from the default key-value store associated with the current actor run.

* **Return type**

  `Any`

***

#### [](#actor-get_value) `async Actor.get_value(key)`

Get a value from the default key-value store associated with the current actor run.

* **Parameters**

  * **key** (`str`) – The key of the record which to retrieve.

* **Return type**

  `Any`

***

#### [](#actor-set_value) `async Actor.set_value(key, value, *, content_type=None)`

Set or delete a value in the default key-value store associated with the current actor run.

* **Parameters**

  * **key** (`str`) – The key of the record which to set.

  * **value** (`any`) – The value of the record which to set, or `None`, if the record should be deleted.

  * **content_type** (`str`, *optional*) – The content type which should be set to the value.

* **Return type**

  `None`

***

#### [](#actor-on) `Actor.on(event_name, listener)`

Add an event listener to the actor’s event manager.

The following events can be emitted:

  * ActorEventTypes.SYSTEM_INFO:

    Emitted every minute, the event data contains info about the resource usage of the actor.

  * ActorEventTypes.MIGRATING:

    Emitted when the actor running on the Apify platform is going to be migrated to another worker server soon.
    You can use it to persist the state of the actor and gracefully stop your in-progress tasks,
    so that they are not interrupted by the migration..

  * ActorEventTypes.PERSIST_STATE:

    Emitted in regular intervals (by default 60 seconds) to notify the actor that it should persist its state,
    in order to avoid repeating all work when the actor restarts.
    This event is automatically emitted together with the migrating event,
    in which case the isMigrating flag in the event data is set to True, otherwise the flag is False.
    Note that this event is provided merely for your convenience,
    you can achieve the same effect using an interval and listening for the migrating event.

  * ActorEventTypes.ABORTING:

    When a user aborts an actor run on the Apify platform,
    they can choose to abort it gracefully, to allow the actor some time before getting terminated.
    This graceful abort emits the aborting event, which you can use to clean up the actor state.

* **Parameters**

  * **event_name** (`ActorEventTypes`) – The actor event for which to listen to.

  * **listener** (`Callable`) – The function which is to be called when the event is emitted (can be async).

* **Return type**

  `Callable`

***

#### [](#actor-off) `Actor.off(event_name, listener=None)`

Remove a listener, or all listeners, from an actor event.

* **Parameters**

  * **event_name** (`ActorEventTypes`) – The actor event for which to remove listeners.

  * **listener** (`Callable`, *optional*) – The listener which is supposed to be removed. If not passed, all listeners of this event are removed.

* **Return type**

  `None`

***

#### [](#actor-is_at_home) `Actor.is_at_home()`

Return True when the actor is running on the Apify platform, and False otherwise (for example when running locally).

* **Return type**

  `bool`

***

#### [](#actor-get_env) `Actor.get_env()`

Return a dictionary with information parsed from all the APIFY_XXX environment variables.

For a list of all the environment variables,
see the [Actor documentation]([https://docs.apify.com/actors/development/environment-variables](https://docs.apify.com/actors/development/environment-variables)).
If some variables are not defined or are invalid, the corresponding value in the resulting dictionary will be None.

* **Return type**

  `Dict`

***

#### [](#actor-start) `async Actor.start(actor_id, run_input=None, *, token=None, content_type=None, build=None, memory_mbytes=None, timeout_secs=None, wait_for_finish=None, webhooks=None)`

Run an actor on the Apify platform.

Unlike Actor.call, this method just starts the run without waiting for finish.

* **Parameters**

  * **actor_id** (`str`) – The ID of the actor to be run.

  * **run_input** (`Any`, *optional*) – The input to pass to the actor run.

  * **token** (`str`, *optional*) – The Apify API token to use for this request (defaults to the APIFY_TOKEN environment variable).

  * **content_type** (`str`, *optional*) – The content type of the input.

  * **build** (`str`, *optional*) – Specifies the actor build to run. It can be either a build tag or build number.
  By default, the run uses the build specified in the default run configuration for the actor (typically latest).

  * **memory_mbytes** (`int`, *optional*) – Memory limit for the run, in megabytes.
  By default, the run uses a memory limit specified in the default run configuration for the actor.

  * **timeout_secs** (`int`, *optional*) – Optional timeout for the run, in seconds.
  By default, the run uses timeout specified in the default run configuration for the actor.

  * **wait_for_finish** (`int`, *optional*) – The maximum number of seconds the server waits for the run to finish.
  By default, it is 0, the maximum value is 300.

  * **webhooks** (`list of dict`, *optional*) – Optional ad-hoc webhooks ([https://docs.apify.com/webhooks/ad-hoc-webhooks](https://docs.apify.com/webhooks/ad-hoc-webhooks))
  associated with the actor run which can be used to receive a notification,
  e.g. when the actor finished or failed.
  If you already have a webhook set up for the actor or task, you do not have to add it again here.
  Each webhook is represented by a dictionary containing these items:
    * `event_types`: list of [`WebhookEventType`](#webhookeventtype) values which trigger the webhook
    * `request_url`: URL to which to send the webhook HTTP request
    * `payload_template` (optional): Optional template for the request payload

* **Returns**

  Info about the started actor run

* **Return type**

  `dict`

***

#### [](#actor-abort) `async Actor.abort(run_id, *, token=None, gracefully=None)`

Abort given actor run on the Apify platform using the current user account (determined by the APIFY_TOKEN environment variable).

* **Parameters**

  * **run_id** (`str`) – The ID of the actor run to be aborted.

  * **token** (`str`, *optional*) – The Apify API token to use for this request (defaults to the APIFY_TOKEN environment variable).

  * **gracefully** (`bool`, *optional*) – If True, the actor run will abort gracefully.
  It will send `aborting` and `persistStates` events into the run and force-stop the run after 30 seconds.
  It is helpful in cases where you plan to resurrect the run later.

* **Returns**

  Info about the aborted actor run

* **Return type**

  `dict`

***

#### [](#actor-call) `async Actor.call(actor_id, run_input=None, *, token=None, content_type=None, build=None, memory_mbytes=None, timeout_secs=None, webhooks=None, wait_secs=None)`

Start an actor on the Apify Platform and wait for it to finish before returning.

It waits indefinitely, unless the wait_secs argument is provided.

* **Parameters**

  * **actor_id** (`str`) – The ID of the actor to be run.

  * **run_input** (`Any`, *optional*) – The input to pass to the actor run.

  * **token** (`str`, *optional*) – The Apify API token to use for this request (defaults to the APIFY_TOKEN environment variable).

  * **content_type** (`str`, *optional*) – The content type of the input.

  * **build** (`str`, *optional*) – Specifies the actor build to run. It can be either a build tag or build number.
  By default, the run uses the build specified in the default run configuration for the actor (typically latest).

  * **memory_mbytes** (`int`, *optional*) – Memory limit for the run, in megabytes.
  By default, the run uses a memory limit specified in the default run configuration for the actor.

  * **timeout_secs** (`int`, *optional*) – Optional timeout for the run, in seconds.
  By default, the run uses timeout specified in the default run configuration for the actor.

  * **webhooks** (`list`, *optional*) – Optional webhooks ([https://docs.apify.com/webhooks](https://docs.apify.com/webhooks)) associated with the actor run,
  which can be used to receive a notification, e.g. when the actor finished or failed.
  If you already have a webhook set up for the actor, you do not have to add it again here.

  * **wait_secs** (`int`, *optional*) – The maximum number of seconds the server waits for the run to finish. If not provided, waits indefinitely.

* **Returns**

  Info about the started actor run

* **Return type**

  `dict`

***

#### [](#actor-call_task) `async Actor.call_task(task_id, task_input=None, *, build=None, memory_mbytes=None, timeout_secs=None, webhooks=None, wait_secs=None, token=None)`

Start an actor task on the Apify Platform and wait for it to finish before returning.

It waits indefinitely, unless the wait_secs argument is provided.

Note that an actor task is a saved input configuration and options for an actor.
If you want to run an actor directly rather than an actor task, please use the Actor.call

* **Parameters**

  * **task_id** (`str`) – The ID of the actor to be run.

  * **task_input** (`Any`, *optional*) – Overrides the input to pass to the actor run.

  * **token** (`str`, *optional*) – The Apify API token to use for this request (defaults to the APIFY_TOKEN environment variable).

  * **content_type** (`str`, *optional*) – The content type of the input.

  * **build** (`str`, *optional*) – Specifies the actor build to run. It can be either a build tag or build number.
  By default, the run uses the build specified in the default run configuration for the actor (typically latest).

  * **memory_mbytes** (`int`, *optional*) – Memory limit for the run, in megabytes.
  By default, the run uses a memory limit specified in the default run configuration for the actor.

  * **timeout_secs** (`int`, *optional*) – Optional timeout for the run, in seconds.
  By default, the run uses timeout specified in the default run configuration for the actor.

  * **webhooks** (`list`, *optional*) – Optional webhooks ([https://docs.apify.com/webhooks](https://docs.apify.com/webhooks)) associated with the actor run,
  which can be used to receive a notification, e.g. when the actor finished or failed.
  If you already have a webhook set up for the actor, you do not have to add it again here.

  * **wait_secs** (`int`, *optional*) – The maximum number of seconds the server waits for the run to finish. If not provided, waits indefinitely.

* **Returns**

  Info about the started actor run

* **Return type**

  `dict`

***

#### [](#actor-metamorph) `async Actor.metamorph(target_actor_id, run_input=None, *, target_actor_build=None, content_type=None, custom_after_sleep_millis=None)`

Transform this actor run to an actor run of a different actor.

The platform stops the current actor container and starts a new container with the new actor instead.
All the default storages are preserved,
and the new input is stored under the INPUT-METAMORPH-1 key in the same default key-value store.

* **Parameters**

  * **target_actor_id** (`str`) – ID of the target actor that the run should be transformed into

  * **run_input** (`Any`, *optional*) – The input to pass to the new run.

  * **target_actor_build** (`str`, *optional*) – The build of the target actor. It can be either a build tag or build number.
  By default, the run uses the build specified in the default run configuration for the target actor (typically the latest build).

  * **content_type** (`str`, *optional*) – The content type of the input.

  * **custom_after_sleep_millis** (`int`, *optional*) – How long to sleep for after the metamorph, to wait for the container to be stopped.

* **Returns**

  The actor run data.

* **Return type**

  `dict`

***

#### [](#actor-reboot) `async Actor.reboot(*, event_listeners_timeout_secs=5)`

Internally reboot this actor.

The system stops the current container and starts a new one, with the same run ID and default storages.

* **Parameters**

  * **event_listeners_timeout_secs** (`int`, *optional*) – How long should the actor wait for actor event listeners to finish before exiting

* **Return type**

  `None`

***

#### [](#actor-add_webhook) `async Actor.add_webhook(*, event_types, request_url, payload_template=None, ignore_ssl_errors=None, do_not_retry=None, idempotency_key=None)`

Create an ad-hoc webhook for the current actor run.

This webhook lets you receive a notification when the actor run finished or failed.

Note that webhooks are only supported for actors running on the Apify platform.
When running the actor locally, the function will print a warning and have no effect.

For more information about Apify actor webhooks, please see the [documentation]([https://docs.apify.com/webhooks](https://docs.apify.com/webhooks)).

* **Parameters**

  * **event_types** ([`list of WebhookEventType`](#webhookeventtype)) – List of event types that should trigger the webhook. At least one is required.

  * **request_url** (`str`) – URL that will be invoked once the webhook is triggered.

  * **payload_template** (`str`, *optional*) – Specification of the payload that will be sent to request_url

  * **ignore_ssl_errors** (`bool`, *optional*) – Whether the webhook should ignore SSL errors returned by request_url

  * **do_not_retry** (`bool`, *optional*) – Whether the webhook should retry sending the payload to request_url upon
  failure.

  * **idempotency_key** (`str`, *optional*) – A unique identifier of a webhook. You can use it to ensure that you won’t
  create the same webhook multiple times.

* **Returns**

  The created webhook

* **Return type**

  `dict`

***

#### [](#actor-set_status_message) `async Actor.set_status_message(status_message, is_terminal=None)`

Set the status message for the current actor run.

* **Parameters**

  * **status_message** (`str`) – The status message to set to the run.

  * **is_terminal** (`bool`, *optional*) – Set this flag to True if this is the final status message of the Actor run.

* **Returns**

  The updated actor run object

* **Return type**

  `dict`

***

#### [](#actor-create_proxy_configuration) `async Actor.create_proxy_configuration(*, actor_proxy_input=None, password=None, groups=None, country_code=None, proxy_urls=None, new_url_function=None)`

Create a ProxyConfiguration object with the passed proxy configuration.

Configures connection to a proxy server with the provided options.
Proxy servers are used to prevent target websites from blocking your crawlers based on IP address rate limits or blacklists.

For more details and code examples, see the ProxyConfiguration class.

* **Parameters**

  * **actor_proxy_input** (`dict`, *optional*) – Proxy configuration field from the actor input, if actor has such input field.
  If you pass this argument, all the other arguments will be inferred from it.

  * **password** (`str`, *optional*) – Password for the Apify Proxy. If not provided, will use os.environ[‘APIFY_PROXY_PASSWORD’], if available.

  * **groups** (`list of str`, *optional*) – Proxy groups which the Apify Proxy should use, if provided.

  * **country_code** (`str`, *optional*) – Country which the Apify Proxy should use, if provided.

  * **proxy_urls** (`list of str`, *optional*) – Custom proxy server URLs which should be rotated through.

  * **new_url_function** (`Callable`, *optional*) – Function which returns a custom proxy URL to be used.

* **Returns**

  ProxyConfiguration object with the passed configuration,

    or `None`, if no proxy should be used based on the configuration.

* **Return type**

  `ProxyConfiguration`, optional

***

### [](#dataset) Dataset

The Dataset class represents a store for structured data where each object stored has the same attributes.

You can imagine it as a table, where each object is a row and its attributes are columns.
Dataset is an append-only storage - you can only add new records to it but you cannot modify or remove existing records.
Typically it is used to store crawling results.

Do not instantiate this class directly, use the Actor.open_dataset() function instead.

Dataset stores its data either on local disk or in the Apify cloud,
depending on whether the APIFY_LOCAL_STORAGE_DIR or APIFY_TOKEN environment variables are set.

If the APIFY_LOCAL_STORAGE_DIR environment variable is set, the data is stored in
the local directory in the following files:
`\`
{APIFY_LOCAL_STORAGE_DIR}/datasets/{DATASET_ID}/{INDEX}.json
\``
Note that {DATASET_ID} is the name or ID of the dataset. The default dataset has ID: default,
unless you override it by setting the APIFY_DEFAULT_DATASET_ID environment variable.
Each dataset item is stored as a separate JSON file, where {INDEX} is a zero-based index of the item in the dataset.

If the APIFY_TOKEN environment variable is set but APIFY_LOCAL_STORAGE_DIR is not, the data is stored in the
[Apify Dataset]([https://docs.apify.com/storage/dataset](https://docs.apify.com/storage/dataset)) cloud storage.

* [async push\_data()](#dataset-push\_data)
* [async get\_data()](#dataset-get\_data)
* [async export\_to()](#dataset-export\_to)
* [async export\_to\_json()](#dataset-export\_to\_json)
* [async export\_to\_csv()](#dataset-export\_to\_csv)
* [async get\_info()](#dataset-get\_info)
* [iterate\_items()](#dataset-iterate\_items)
* [async drop()](#dataset-drop)
* [async open()](#dataset-open)

***

#### [](#dataset-push_data) `async Dataset.push_data(data)`

Store an object or an array of objects to the dataset.

The size of the data is limited by the receiving API and therefore push_data() will only
allow objects whose JSON representation is smaller than 9MB. When an array is passed,
none of the included objects may be larger than 9MB, but the array itself may be of any size.

* **Parameters**

  * **data** (`JSONSerializable`) – dict or array of dicts containing data to be stored in the default dataset.
  The JSON representation of each item must be smaller than 9MB.

* **Return type**

  `None`

***

#### [](#dataset-get_data) `async Dataset.get_data(*, offset=None, limit=None, clean=None, desc=None, fields=None, omit=None, unwind=None, skip_empty=None, skip_hidden=None, flatten=None, view=None)`

Get items from the dataset.

* **Parameters**

  * **offset** (`int`, *optional*) – Number of items that should be skipped at the start. The default value is 0

  * **limit** (`int`, *optional*) – Maximum number of items to return. By default there is no limit.

  * **desc** (`bool`, *optional*) – By default, results are returned in the same order as they were stored.
  To reverse the order, set this parameter to True.

  * **clean** (`bool`, *optional*) – If True, returns only non-empty items and skips hidden fields (i.e. fields starting with the # character).
  The clean parameter is just a shortcut for skip_hidden=True and skip_empty=True parameters.
  Note that since some objects might be skipped from the output, that the result might contain less items than the limit value.

  * **fields** (`list of str`, *optional*) – A list of fields which should be picked from the items,
  only these fields will remain in the resulting record objects.
  Note that the fields in the outputted items are sorted the same way as they are specified in the fields parameter.
  You can use this feature to effectively fix the output format.

  * **omit** (`list of str`, *optional*) – A list of fields which should be omitted from the items.

  * **unwind** (`str`, *optional*) – Name of a field which should be unwound.
  If the field is an array then every element of the array will become a separate record and merged with parent object.
  If the unwound field is an object then it is merged with the parent object.
  If the unwound field is missing or its value is neither an array nor an object and therefore cannot be merged with a parent object,
  then the item gets preserved as it is. Note that the unwound items ignore the desc parameter.

  * **skip_empty** (`bool`, *optional*) – If True, then empty items are skipped from the output.
  Note that if used, the results might contain less items than the limit value.

  * **skip_hidden** (`bool`, *optional*) – If True, then hidden fields are skipped from the output, i.e. fields starting with the # character.

  * **flatten** (`list of str`, *optional*) – A list of fields that should be flattened

  * **view** (`str`, *optional*) – Name of the dataset view to be used

* **Returns**

  A page of the list of dataset items according to the specified filters.

* **Return type**

  [`ListPage`](#listpage)

***

#### [](#dataset-export_to) `async Dataset.export_to(key, *, to_key_value_store_id=None, to_key_value_store_name=None, content_type=None)`

Save the entirety of the dataset’s contents into one file within a key-value store.

* **Parameters**

  * **key** (`str`) – The key to save the data under.

  * **to_key_value_store_id** (`str`, *optional*) – The id of the key-value store in which the result will be saved.

  * **to_key_value_store_name** (`str`, *optional*) – The name of the key-value store in which the result will be saved.
  You must specify only one of to_key_value_store_id and to_key_value_store_name arguments.
  If you omit both, it uses the default key-value store.

  * **content_type** (`str`, *optional*) – Either ‘text/csv’ or ‘application/json’. Defaults to JSON.

* **Return type**

  `None`

***

#### [](#dataset-export_to_json) `async Dataset.export_to_json(key, *, from_dataset_id=None, from_dataset_name=None, to_key_value_store_id=None, to_key_value_store_name=None)`

Save the entirety of the dataset’s contents into one JSON file within a key-value store.

* **Parameters**

  * **key** (`str`) – The key to save the data under.

  * **from_dataset_id** (`str`, *optional*) – The ID of the dataset in case of calling the class method. Uses default dataset if omitted.

  * **from_dataset_name** (`str`, *optional*) – The name of the dataset in case of calling the class method. Uses default dataset if omitted.
  You must specify only one of from_dataset_id and from_dataset_name arguments.
  If you omit both, it uses the default dataset.

  * **to_key_value_store_id** (`str`, *optional*) – The id of the key-value store in which the result will be saved.

  * **to_key_value_store_name** (`str`, *optional*) – The name of the key-value store in which the result will be saved.
  You must specify only one of to_key_value_store_id and to_key_value_store_name arguments.
  If you omit both, it uses the default key-value store.

* **Return type**

  `None`

***

#### [](#dataset-export_to_csv) `async Dataset.export_to_csv(key, *, from_dataset_id=None, from_dataset_name=None, to_key_value_store_id=None, to_key_value_store_name=None)`

Save the entirety of the dataset’s contents into one CSV file within a key-value store.

* **Parameters**

  * **key** (`str`) – The key to save the data under.

  * **from_dataset_id** (`str`, *optional*) – The ID of the dataset in case of calling the class method. Uses default dataset if omitted.

  * **from_dataset_name** (`str`, *optional*) – The name of the dataset in case of calling the class method. Uses default dataset if omitted.
  You must specify only one of from_dataset_id and from_dataset_name arguments.
  If you omit both, it uses the default dataset.

  * **to_key_value_store_id** (`str`, *optional*) – The id of the key-value store in which the result will be saved.

  * **to_key_value_store_name** (`str`, *optional*) – The name of the key-value store in which the result will be saved.
  You must specify only one of to_key_value_store_id and to_key_value_store_name arguments.
  If you omit both, it uses the default key-value store.

* **Return type**

  `None`

***

#### [](#dataset-get_info) `async Dataset.get_info()`

Get an object containing general information about the dataset.

* **Returns**

  Object returned by calling the GET dataset API endpoint.

* **Return type**

  `dict`

***

#### [](#dataset-iterate_items) `Dataset.iterate_items(*, offset=0, limit=None, clean=None, desc=None, fields=None, omit=None, unwind=None, skip_empty=None, skip_hidden=None)`

Iterate over the items in the dataset.

* **Parameters**

  * **offset** (`int`, *optional*) – Number of items that should be skipped at the start. The default value is 0

  * **limit** (`int`, *optional*) – Maximum number of items to return. By default there is no limit.

  * **desc** (`bool`, *optional*) – By default, results are returned in the same order as they were stored.
  To reverse the order, set this parameter to True.

  * **clean** (`bool`, *optional*) – If True, returns only non-empty items and skips hidden fields (i.e. fields starting with the # character).
  The clean parameter is just a shortcut for skip_hidden=True and skip_empty=True parameters.
  Note that since some objects might be skipped from the output, that the result might contain less items than the limit value.

  * **fields** (`list of str`, *optional*) – A list of fields which should be picked from the items,
  only these fields will remain in the resulting record objects.
  Note that the fields in the outputted items are sorted the same way as they are specified in the fields parameter.
  You can use this feature to effectively fix the output format.

  * **omit** (`list of str`, *optional*) – A list of fields which should be omitted from the items.

  * **unwind** (`str`, *optional*) – Name of a field which should be unwound.
  If the field is an array then every element of the array will become a separate record and merged with parent object.
  If the unwound field is an object then it is merged with the parent object.
  If the unwound field is missing or its value is neither an array nor an object and therefore cannot be merged with a parent object,
  then the item gets preserved as it is. Note that the unwound items ignore the desc parameter.

  * **skip_empty** (`bool`, *optional*) – If True, then empty items are skipped from the output.
  Note that if used, the results might contain less items than the limit value.

  * **skip_hidden** (`bool`, *optional*) – If True, then hidden fields are skipped from the output, i.e. fields starting with the # character.

* **Yields**

  `dict` – An item from the dataset

* **Return type**

  `AsyncIterator[Dict]`

***

#### [](#dataset-drop) `async Dataset.drop()`

Remove the dataset either from the Apify cloud storage or from the local directory.

* **Return type**

  `None`

***

#### [](#dataset-open) `async Dataset.open(*, id=None, name=None, force_cloud=False, config=None)`

Open a dataset.

Datasets are used to store structured data where each object stored has the same attributes,
such as online store products or real estate offers.
The actual data is stored either on the local filesystem or in the Apify cloud.

* **Parameters**

  * **id** (`str`, *optional*) – ID of the dataset to be opened.
  If neither id nor name are provided, the method returns the default dataset associated with the actor run.
  If the dataset with the given ID does not exist, it raises an error.

  * **name** (`str`, *optional*) – Name of the dataset to be opened.
  If neither id nor name are provided, the method returns the default dataset associated with the actor run.
  If the dataset with the given name does not exist, it is created.

  * **force_cloud** (`bool`, *optional*) – If set to True, it will open a dataset on the Apify Platform even when running the actor locally.
  Defaults to False.

  * **config** (`Configuration`, *optional*) – A Configuration instance, uses global configuration if omitted.

* **Returns**

  An instance of the Dataset class for the given ID or name.

* **Return type**

  `Dataset`

***

### [](#keyvaluestore) KeyValueStore

The KeyValueStore class represents a key-value store.

You can imagine it as a simple data storage that is used
for saving and reading data records or files. Each data record is
represented by a unique key and associated with a MIME content type.

Do not instantiate this class directly, use the Actor.open_key_value_store() function instead.

Each crawler run is associated with a default key-value store, which is created exclusively
for the run. By convention, the crawler input and output are stored into the
default key-value store under the INPUT and OUTPUT key, respectively.
Typically, input and output are JSON files, although it can be any other format.
To access the default key-value store directly, you can use the
KeyValueStore.get_value and KeyValueStore.set_value convenience functions.

KeyValueStore stores its data either on local disk or in the Apify cloud,
depending on whether the APIFY_LOCAL_STORAGE_DIR or APIFY_TOKEN environment variables are set.

If the APIFY_LOCAL_STORAGE_DIR environment variable is set, the data is stored in
the local directory in the following files:
`\`
{APIFY_LOCAL_STORAGE_DIR}/key_value_stores/{STORE_ID}/{INDEX}.{EXT}
\``
Note that {STORE_ID} is the name or ID of the key-value store. The default key-value store has ID: default,
unless you override it by setting the APIFY_DEFAULT_KEY_VALUE_STORE_ID environment variable.
The {KEY} is the key of the record and {EXT} corresponds to the MIME content type of the data value.

If the APIFY_TOKEN environment variable is set but APIFY_LOCAL_STORAGE_DIR is not, the data is stored in the
[Apify Key-value store]([https://docs.apify.com/storage/key-value-store](https://docs.apify.com/storage/key-value-store)) cloud storage.

* [async get\_value()](#keyvaluestore-get\_value)
* [async iterate\_keys()](#keyvaluestore-iterate\_keys)
* [async set\_value()](#keyvaluestore-set\_value)
* [async get\_public\_url()](#keyvaluestore-get\_public\_url)
* [async drop()](#keyvaluestore-drop)
* [async open()](#keyvaluestore-open)

***

#### [](#keyvaluestore-get_value) `async KeyValueStore.get_value(key, default_value=None)`

Get a value from the key-value store.

* **Parameters**

  * **key** (`str`) – Key of the record to retrieve.

  * **default_value** (`Any`, *optional*) – Default value returned in case the record does not exist.

* **Returns**

  The value associated with the given key. default_value is used in case the record does not exist.

* **Return type**

  `Any`

***

#### [](#keyvaluestore-iterate_keys) `async KeyValueStore.iterate_keys(exclusive_start_key=None)`

Iterate over the keys in the key-value store.

* **Parameters**

  * **exclusive_start_key** (`str`, *optional*) – All keys up to this one (including) are skipped from the result.

* **Yields**

  `IterateKeysTuple` –

  A tuple (key, info),

    where key is the record key, and info is an object that contains a single property size
    indicating size of the record in bytes.

* **Return type**

  `AsyncIterator[IterateKeysTuple]`

***

#### [](#keyvaluestore-set_value) `async KeyValueStore.set_value(key, value, content_type=None)`

Set or delete a value in the key-value store.

* **Parameters**

  * **key** (`str`) – The key under which the value should be saved.

  * **value** (`Any`, *optional*) – The value to save. If the value is `None`, the corresponding key-value pair will be deleted.

  * **content_type** (`str`, *optional*) – The content type of the saved value.

* **Return type**

  `None`

***

#### [](#keyvaluestore-get_public_url) `async KeyValueStore.get_public_url(key)`

Get a URL for the given key that may be used to publicly access the value in the remote key-value store.

* **Parameters**

  * **key** (`str`) – The key for which the URL should be generated.

* **Return type**

  `str`

***

#### [](#keyvaluestore-drop) `async KeyValueStore.drop()`

Remove the key-value store either from the Apify cloud storage or from the local directory.

* **Return type**

  `None`

***

#### [](#keyvaluestore-open) `async KeyValueStore.open(*, id=None, name=None, force_cloud=False, config=None)`

Open a key-value store.

Key-value stores are used to store records or files, along with their MIME content type.
The records are stored and retrieved using a unique key.
The actual data is stored either on a local filesystem or in the Apify cloud.

* **Parameters**

  * **id** (`str`, *optional*) – ID of the key-value store to be opened.
  If neither id nor name are provided, the method returns the default key-value store associated with the actor run.
  If the key-value store with the given ID does not exist, it raises an error.

  * **name** (`str`, *optional*) – Name of the key-value store to be opened.
  If neither id nor name are provided, the method returns the default key-value store associated with the actor run.
  If the key-value store with the given name does not exist, it is created.

  * **force_cloud** (`bool`, *optional*) – If set to True, it will open a key-value store on the Apify Platform even when running the actor locally.
  Defaults to False.

  * **config** (`Configuration`, *optional*) – A Configuration instance, uses global configuration if omitted.

* **Returns**

  An instance of the KeyValueStore class for the given ID or name.

* **Return type**

  `KeyValueStore`

***

### [](#requestqueue) RequestQueue

Represents a queue of URLs to crawl.

Can be used for deep crawling of websites where you start with several URLs and then recursively
follow links to other pages. The data structure supports both breadth-first and depth-first crawling orders.

Each URL is represented using an instance of the [{@apilink](mailto:{@apilink) Request} class.
The queue can only contain unique URLs. More precisely, it can only contain request dictionaries
with distinct uniqueKey properties. By default, uniqueKey is generated from the URL, but it can also be overridden.
To add a single URL multiple times to the queue,
corresponding request dictionary will need to have different uniqueKey properties.

Do not instantiate this class directly, use the Actor.open_request_queue() function instead.

RequestQueue stores its data either on local disk or in the Apify cloud,
depending on whether the APIFY_LOCAL_STORAGE_DIR or APIFY_TOKEN environment variables are set.

If the APIFY_LOCAL_STORAGE_DIR environment variable is set, the data is stored in
the local directory in the following files:
`\`
{APIFY_LOCAL_STORAGE_DIR}/request_queues/{QUEUE_ID}/{REQUEST_ID}.json
\``
Note that {QUEUE_ID} is the name or ID of the request queue. The default request queue has ID: default,
unless you override it by setting the APIFY_DEFAULT_REQUEST_QUEUE_ID environment variable.
The {REQUEST_ID} is the id of the request.

If the APIFY_TOKEN environment variable is set but APIFY_LOCAL_STORAGE_DIR is not, the data is stored in the
[Apify Request Queue]([https://docs.apify.com/storage/request-queue](https://docs.apify.com/storage/request-queue))
cloud storage.

* [async add\_request()](#requestqueue-add\_request)
* [async get\_request()](#requestqueue-get\_request)
* [async fetch\_next\_request()](#requestqueue-fetch\_next\_request)
* [async mark\_request\_as\_handled()](#requestqueue-mark\_request\_as\_handled)
* [async reclaim\_request()](#requestqueue-reclaim\_request)
* [async is\_empty()](#requestqueue-is\_empty)
* [async is\_finished()](#requestqueue-is\_finished)
* [async drop()](#requestqueue-drop)
* [async get\_info()](#requestqueue-get\_info)
* [async open()](#requestqueue-open)

***

#### [](#requestqueue-add_request) `async RequestQueue.add_request(request, *, forefront=False)`

Add a request to the queue.

* **Parameters**

  * **request** (`dict`) – The request to add to the queue

  * **forefront** (`bool`, *optional*) – Whether to add the request to the head or the end of the queue

* **Returns**

  Information about the queue operation with keys requestId, uniqueKey, wasAlreadyPresent, wasAlreadyHandled.

* **Return type**

  `dict`

***

#### [](#requestqueue-get_request) `async RequestQueue.get_request(request_id)`

Retrieve a request from the queue.

* **Parameters**

  * **request_id** (`str`) – ID of the request to retrieve.

* **Returns**

  The retrieved request, or `None`, if it does not exist.

* **Return type**

  `dict`, optional

***

#### [](#requestqueue-fetch_next_request) `async RequestQueue.fetch_next_request()`

Return the next request in the queue to be processed.

Once you successfully finish processing of the request, you need to call
RequestQueue.mark_request_as_handled to mark the request as handled in the queue.
If there was some error in processing the request, call RequestQueue.reclaim_request instead,
so that the queue will give the request to some other consumer in another call to the fetch_next_request method.

Note that the `None` return value does not mean the queue processing finished, it means there are currently no pending requests.
To check whether all requests in queue were finished, use RequestQueue.is_finished instead.

* **Returns**

  The request or `None` if there are no more pending requests.

* **Return type**

  `dict`, optional

***

#### [](#requestqueue-mark_request_as_handled) `async RequestQueue.mark_request_as_handled(request)`

Mark a request as handled after successful processing.

Handled requests will never again be returned by the RequestQueue.fetch_next_request method.

* **Parameters**

  * **request** (`dict`) – The request to mark as handled.

* **Returns**

  Information about the queue operation with keys requestId, uniqueKey, wasAlreadyPresent, wasAlreadyHandled.

    `None` if the given request was not in progress.

* **Return type**

  `dict`, optional

***

#### [](#requestqueue-reclaim_request) `async RequestQueue.reclaim_request(request, forefront=False)`

Reclaim a failed request back to the queue.

The request will be returned for processing later again
by another call to RequestQueue.fetchNextRequest.

* **Parameters**

  * **request** (`dict`) – The request to return to the queue.

  * **forefront** (`bool`, *optional*) – Whether to add the request to the head or the end of the queue

* **Returns**

  Information about the queue operation with keys requestId, uniqueKey, wasAlreadyPresent, wasAlreadyHandled.

    `None` if the given request was not in progress.

* **Return type**

  `dict`, optional

***

#### [](#requestqueue-is_empty) `async RequestQueue.is_empty()`

Check whether the queue is empty.

* **Returns**

  True if the next call to RequestQueue.fetchNextRequest would return `None`, otherwise False.

* **Return type**

  `bool`

***

#### [](#requestqueue-is_finished) `async RequestQueue.is_finished()`

Check whether the queue is finished.

Due to the nature of distributed storage used by the queue,
the function might occasionally return a false negative,
but it will never return a false positive.

* **Returns**

  True if all requests were already handled and there are no more left. False otherwise.

* **Return type**

  `bool`

***

#### [](#requestqueue-drop) `async RequestQueue.drop()`

Remove the request queue either from the Apify cloud storage or from the local directory.

* **Return type**

  `None`

***

#### [](#requestqueue-get_info) `async RequestQueue.get_info()`

Get an object containing general information about the request queue.

* **Returns**

  Object returned by calling the GET request queue API endpoint.

* **Return type**

  `dict`

***

#### [](#requestqueue-open) `async RequestQueue.open(*, id=None, name=None, force_cloud=False, config=None)`

Open a request queue.

Request queue represents a queue of URLs to crawl, which is stored either on local filesystem or in the Apify cloud.
The queue is used for deep crawling of websites, where you start with several URLs and then
recursively follow links to other pages. The data structure supports both breadth-first
and depth-first crawling orders.

* **Parameters**

  * **id** (`str`, *optional*) – ID of the request queue to be opened.
  If neither id nor name are provided, the method returns the default request queue associated with the actor run.
  If the request queue with the given ID does not exist, it raises an error.

  * **name** (`str`, *optional*) – Name of the request queue to be opened.
  If neither id nor name are provided, the method returns the default request queue associated with the actor run.
  If the request queue with the given name does not exist, it is created.

  * **force_cloud** (`bool`, *optional*) – If set to True, it will open a request queue on the Apify Platform even when running the actor locally.
  Defaults to False.

  * **config** (`Configuration`, *optional*) – A Configuration instance, uses global configuration if omitted.

* **Returns**

  An instance of the RequestQueue class for the given ID or name.

* **Return type**

  `RequestQueue`

***

### [](#proxyconfiguration) ProxyConfiguration

Configures a connection to a proxy server with the provided options.

Proxy servers are used to prevent target websites from blocking your crawlers based on IP address rate limits or blacklists.
The default servers used by this class are managed by [Apify Proxy]([https://docs.apify.com/proxy](https://docs.apify.com/proxy)).
To be able to use Apify Proxy, you need an Apify account and access to the selected proxies. If you provide no configuration option,
the proxies will be managed automatically using a smart algorithm.

If you want to use your own proxies, use the proxy_urls or new_url_function constructor options.
Your list of proxy URLs will be rotated by the configuration, if this option is provided.

* [async initialize()](#proxyconfiguration-initialize)
* [async new\_url()](#proxyconfiguration-new\_url)
* [async new\_proxy\_info()](#proxyconfiguration-new\_proxy\_info)

***

#### [](#proxyconfiguration-initialize) `async ProxyConfiguration.initialize()`

Load the Apify Proxy password if the API token is provided and check access to Apify Proxy and provided proxy groups.

Only called if Apify Proxy configuration is used.
Also checks if country has access to Apify Proxy groups if the country code is provided.

You should use the Actor.create_proxy_configuration function
to create a pre-initialized ProxyConfiguration instance instead of calling this manually.

* **Return type**

  `None`

***

#### [](#proxyconfiguration-new_url) `async ProxyConfiguration.new_url(session_id=None)`

Return a new proxy URL based on provided configuration options and the sessionId parameter.

* **Parameters**

  * **session_id** (`int or str`, *optional*) – Represents the identifier of a proxy session ([https://docs.apify.com/proxy#sessions](https://docs.apify.com/proxy#sessions)).

  * **identifier** (*All the HTTP requests going through the proxy with the same session*) – 

  * **server** (*will use the same target proxy*) – 

  * **following** (*The identifier must not be longer than 50 characters and include only the*) – 0-9, a-z, A-Z, “.”, “_” and “~”.

* **Returns**

  A string with a proxy URL, including authentication credentials and port number.

    For example, http://bob:password123@proxy.example.com:8000

* **Return type**

  `str`

***

#### [](#proxyconfiguration-new_proxy_info) `async ProxyConfiguration.new_proxy_info(session_id=None)`

Create a new ProxyInfo object.

Use it if you want to work with a rich representation of a proxy URL.
If you need the URL string only, use ProxyConfiguration.new_url.

* **Parameters**

  * **session_id** (`int or str`, *optional*) – Represents the identifier of a proxy session ([https://docs.apify.com/proxy#sessions](https://docs.apify.com/proxy#sessions)).

  * **identifier** (*All the HTTP requests going through the proxy with the same session*) – 

  * **server** (*will use the same target proxy*) – 

  * **following** (*The identifier must not be longer than 50 characters and include only the*) – 0-9, a-z, A-Z, “.”, “_” and “~”.

* **Returns**

  Dictionary that represents information about the proxy and its configuration.

* **Return type**

  `ProxyInfo`

***

### [](#proxyinfo) ProxyInfo()

Provides information about a proxy connection that is used for requests.

#### Instance attributes

Name | Type | Description
---- | ---- | -----------
`url` | `` | The URL of the proxy.
`hostname` | `` | The hostname of the proxy.
`port` | `` | The proxy port.
`username` | `` | The username for the proxy.
`password` | `` | The password for the proxy.
`groups` | `An` | //docs.apify.com/proxy).If not provided, the proxy will select the groups automatically.
`country\_code` | `` | If set and relevant proxies are available in your Apify account, all proxied requests willuse IP addresses that are geolocated to the specified country. For example GB for IPsfrom Great Britain. Note that online services often have their own rules for handlinggeolocation and thus the country selection is a best attempt at geolocation, rather thana guaranteed hit. This parameter is optional, by default, each proxied request is assignedan IP address from a random country. The country code needs to be a two letter ISO country code.See the [full list of available country codes]([https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2#Officially_assigned_code_elements](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2#Officially_assigned_code_elements)).This parameter is optional, by default, the proxy uses all available proxy servers from all countries.
`session\_id` | `` | The identifier of the used proxy session, if used. Using the same session ID guarantees getting the same proxy URL.

***

### [](#configuration) Configuration

A class for specifying the configuration of an actor.

Can be used either globally via Configuration.get_global_configuration(),
or it can be specific to each Actor instance on the actor.config property.

* [get\_global\_configuration()](#configuration-get\_global\_configuration)

***

#### [](#configuration-get_global_configuration) `Configuration.get_global_configuration()`

Retrive the global configuration.

The global configuration applies when you call actor methods via their static versions, e.g. Actor.init().
Also accessible via Actor.config.

* **Return type**

  `Configuration`

***

### [](#actoreventtypes) ActorEventTypes

Possible values of actor event type.

* [SYSTEM\_INFO](#actoreventtypes-system\_info)
* [MIGRATING](#actoreventtypes-migrating)
* [PERSIST\_STATE](#actoreventtypes-persist\_state)
* [ABORTING](#actoreventtypes-aborting)

***

#### [](#actoreventtypes-system_info) `ActorEventTypes.SYSTEM_INFO`

Info about resource usage of the actor

***

#### [](#actoreventtypes-migrating) `ActorEventTypes.MIGRATING`

Sent when the actor is about to migrate

***

#### [](#actoreventtypes-persist_state) `ActorEventTypes.PERSIST_STATE`

Sent when the actor should persist its state (every minute or when migrating)

***

#### [](#actoreventtypes-aborting) `ActorEventTypes.ABORTING`

Sent when the actor is aborting

***

### [](#apifyenvvars) ApifyEnvVars

Possible Apify-specific environment variables.

* [ACT\_ID](#apifyenvvars-act\_id)
* [ACT\_RUN\_ID](#apifyenvvars-act\_run\_id)
* [ACTOR\_BUILD\_ID](#apifyenvvars-actor\_build\_id)
* [ACTOR\_BUILD\_NUMBER](#apifyenvvars-actor\_build\_number)
* [ACTOR\_EVENTS\_WS\_URL](#apifyenvvars-actor\_events\_ws\_url)
* [ACTOR\_ID](#apifyenvvars-actor\_id)
* [ACTOR\_RUN\_ID](#apifyenvvars-actor\_run\_id)
* [ACTOR\_TASK\_ID](#apifyenvvars-actor\_task\_id)
* [API\_BASE\_URL](#apifyenvvars-api\_base\_url)
* [API\_PUBLIC\_BASE\_URL](#apifyenvvars-api\_public\_base\_url)
* [CHROME\_EXECUTABLE\_PATH](#apifyenvvars-chrome\_executable\_path)
* [CONTAINER\_PORT](#apifyenvvars-container\_port)
* [CONTAINER\_URL](#apifyenvvars-container\_url)
* [DEDICATED\_CPUS](#apifyenvvars-dedicated\_cpus)
* [DEFAULT\_BROWSER\_PATH](#apifyenvvars-default\_browser\_path)
* [DEFAULT\_DATASET\_ID](#apifyenvvars-default\_dataset\_id)
* [DEFAULT\_KEY\_VALUE\_STORE\_ID](#apifyenvvars-default\_key\_value\_store\_id)
* [DEFAULT\_REQUEST\_QUEUE\_ID](#apifyenvvars-default\_request\_queue\_id)
* [DISABLE\_BROWSER\_SANDBOX](#apifyenvvars-disable\_browser\_sandbox)
* [DISABLE\_OUTDATED\_WARNING](#apifyenvvars-disable\_outdated\_warning)
* [FACT](#apifyenvvars-fact)
* [HEADLESS](#apifyenvvars-headless)
* [INPUT\_KEY](#apifyenvvars-input\_key)
* [INPUT\_SECRETS\_PRIVATE\_KEY\_FILE](#apifyenvvars-input\_secrets\_private\_key\_file)
* [INPUT\_SECRETS\_PRIVATE\_KEY\_PASSPHRASE](#apifyenvvars-input\_secrets\_private\_key\_passphrase)
* [IS\_AT\_HOME](#apifyenvvars-is\_at\_home)
* [LOCAL\_STORAGE\_DIR](#apifyenvvars-local\_storage\_dir)
* [LOG\_FORMAT](#apifyenvvars-log\_format)
* [LOG\_LEVEL](#apifyenvvars-log\_level)
* [MAX\_USED\_CPU\_RATIO](#apifyenvvars-max\_used\_cpu\_ratio)
* [MEMORY\_MBYTES](#apifyenvvars-memory\_mbytes)
* [META\_ORIGIN](#apifyenvvars-meta\_origin)
* [PERSIST\_STORAGE](#apifyenvvars-persist\_storage)
* [PROXY\_HOSTNAME](#apifyenvvars-proxy\_hostname)
* [PROXY\_PASSWORD](#apifyenvvars-proxy\_password)
* [PROXY\_PORT](#apifyenvvars-proxy\_port)
* [PROXY\_STATUS\_URL](#apifyenvvars-proxy\_status\_url)
* [SDK\_LATEST\_VERSION](#apifyenvvars-sdk\_latest\_version)
* [STARTED\_AT](#apifyenvvars-started\_at)
* [TIMEOUT\_AT](#apifyenvvars-timeout\_at)
* [TOKEN](#apifyenvvars-token)
* [USER\_ID](#apifyenvvars-user\_id)
* [WORKFLOW\_KEY](#apifyenvvars-workflow\_key)
* [XVFB](#apifyenvvars-xvfb)
* [METAMORPH\_AFTER\_SLEEP\_MILLIS](#apifyenvvars-metamorph\_after\_sleep\_millis)
* [PERSIST\_STATE\_INTERVAL\_MILLIS](#apifyenvvars-persist\_state\_interval\_millis)
* [PURGE\_ON\_START](#apifyenvvars-purge\_on\_start)
* [SYSTEM\_INFO\_INTERVAL\_MILLIS](#apifyenvvars-system\_info\_interval\_millis)

***

#### [](#apifyenvvars-act_id) `ApifyEnvVars.ACT_ID`

ACT_ID

***

#### [](#apifyenvvars-act_run_id) `ApifyEnvVars.ACT_RUN_ID`

ACT_RUN_ID

***

#### [](#apifyenvvars-actor_build_id) `ApifyEnvVars.ACTOR_BUILD_ID`

ACTOR_BUILD_ID

***

#### [](#apifyenvvars-actor_build_number) `ApifyEnvVars.ACTOR_BUILD_NUMBER`

ACTOR_BUILD_NUMBER

***

#### [](#apifyenvvars-actor_events_ws_url) `ApifyEnvVars.ACTOR_EVENTS_WS_URL`

ACTOR_EVENTS_WS_URL

***

#### [](#apifyenvvars-actor_id) `ApifyEnvVars.ACTOR_ID`

ACTOR_ID

***

#### [](#apifyenvvars-actor_run_id) `ApifyEnvVars.ACTOR_RUN_ID`

ACTOR_RUN_ID

***

#### [](#apifyenvvars-actor_task_id) `ApifyEnvVars.ACTOR_TASK_ID`

ACTOR_TASK_ID

***

#### [](#apifyenvvars-api_base_url) `ApifyEnvVars.API_BASE_URL`

API_BASE_URL

***

#### [](#apifyenvvars-api_public_base_url) `ApifyEnvVars.API_PUBLIC_BASE_URL`

API_PUBLIC_BASE_URL

***

#### [](#apifyenvvars-chrome_executable_path) `ApifyEnvVars.CHROME_EXECUTABLE_PATH`

CHROME_EXECUTABLE_PATH

***

#### [](#apifyenvvars-container_port) `ApifyEnvVars.CONTAINER_PORT`

CONTAINER_PORT

***

#### [](#apifyenvvars-container_url) `ApifyEnvVars.CONTAINER_URL`

CONTAINER_URL

***

#### [](#apifyenvvars-dedicated_cpus) `ApifyEnvVars.DEDICATED_CPUS`

DEDICATED_CPUS

***

#### [](#apifyenvvars-default_browser_path) `ApifyEnvVars.DEFAULT_BROWSER_PATH`

DEFAULT_BROWSER_PATH

***

#### [](#apifyenvvars-default_dataset_id) `ApifyEnvVars.DEFAULT_DATASET_ID`

DEFAULT_DATASET_ID

***

#### [](#apifyenvvars-default_key_value_store_id) `ApifyEnvVars.DEFAULT_KEY_VALUE_STORE_ID`

DEFAULT_KEY_VALUE_STORE_ID

***

#### [](#apifyenvvars-default_request_queue_id) `ApifyEnvVars.DEFAULT_REQUEST_QUEUE_ID`

DEFAULT_REQUEST_QUEUE_ID

***

#### [](#apifyenvvars-disable_browser_sandbox) `ApifyEnvVars.DISABLE_BROWSER_SANDBOX`

DISABLE_BROWSER_SANDBOX

***

#### [](#apifyenvvars-disable_outdated_warning) `ApifyEnvVars.DISABLE_OUTDATED_WARNING`

DISABLE_OUTDATED_WARNING

***

#### [](#apifyenvvars-fact) `ApifyEnvVars.FACT`

FACT

***

#### [](#apifyenvvars-headless) `ApifyEnvVars.HEADLESS`

HEADLESS

***

#### [](#apifyenvvars-input_key) `ApifyEnvVars.INPUT_KEY`

INPUT_KEY

***

#### [](#apifyenvvars-input_secrets_private_key_file) `ApifyEnvVars.INPUT_SECRETS_PRIVATE_KEY_FILE`

INPUT_SECRETS_PRIVATE_KEY_FILE

***

#### [](#apifyenvvars-input_secrets_private_key_passphrase) `ApifyEnvVars.INPUT_SECRETS_PRIVATE_KEY_PASSPHRASE`

INPUT_SECRETS_PRIVATE_KEY_PASSPHRASE

***

#### [](#apifyenvvars-is_at_home) `ApifyEnvVars.IS_AT_HOME`

IS_AT_HOME

***

#### [](#apifyenvvars-local_storage_dir) `ApifyEnvVars.LOCAL_STORAGE_DIR`

LOCAL_STORAGE_DIR

***

#### [](#apifyenvvars-log_format) `ApifyEnvVars.LOG_FORMAT`

LOG_FORMAT

***

#### [](#apifyenvvars-log_level) `ApifyEnvVars.LOG_LEVEL`

LOG_LEVEL

***

#### [](#apifyenvvars-max_used_cpu_ratio) `ApifyEnvVars.MAX_USED_CPU_RATIO`

MAX_USED_CPU_RATIO

***

#### [](#apifyenvvars-memory_mbytes) `ApifyEnvVars.MEMORY_MBYTES`

MEMORY_MBYTES

***

#### [](#apifyenvvars-meta_origin) `ApifyEnvVars.META_ORIGIN`

META_ORIGIN

***

#### [](#apifyenvvars-persist_storage) `ApifyEnvVars.PERSIST_STORAGE`

PERSIST_STORAGE

***

#### [](#apifyenvvars-proxy_hostname) `ApifyEnvVars.PROXY_HOSTNAME`

PROXY_HOSTNAME

***

#### [](#apifyenvvars-proxy_password) `ApifyEnvVars.PROXY_PASSWORD`

PROXY_PASSWORD

***

#### [](#apifyenvvars-proxy_port) `ApifyEnvVars.PROXY_PORT`

PROXY_PORT

***

#### [](#apifyenvvars-proxy_status_url) `ApifyEnvVars.PROXY_STATUS_URL`

PROXY_STATUS_URL

***

#### [](#apifyenvvars-sdk_latest_version) `ApifyEnvVars.SDK_LATEST_VERSION`

SDK_LATEST_VERSION

***

#### [](#apifyenvvars-started_at) `ApifyEnvVars.STARTED_AT`

STARTED_AT

***

#### [](#apifyenvvars-timeout_at) `ApifyEnvVars.TIMEOUT_AT`

TIMEOUT_AT

***

#### [](#apifyenvvars-token) `ApifyEnvVars.TOKEN`

TOKEN

***

#### [](#apifyenvvars-user_id) `ApifyEnvVars.USER_ID`

USER_ID

***

#### [](#apifyenvvars-workflow_key) `ApifyEnvVars.WORKFLOW_KEY`

WORKFLOW_KEY

***

#### [](#apifyenvvars-xvfb) `ApifyEnvVars.XVFB`

XVFB

***

#### [](#apifyenvvars-metamorph_after_sleep_millis) `ApifyEnvVars.METAMORPH_AFTER_SLEEP_MILLIS`

METAMORPH_AFTER_SLEEP_MILLIS

***

#### [](#apifyenvvars-persist_state_interval_millis) `ApifyEnvVars.PERSIST_STATE_INTERVAL_MILLIS`

PERSIST_STATE_INTERVAL_MILLIS

***

#### [](#apifyenvvars-purge_on_start) `ApifyEnvVars.PURGE_ON_START`

PURGE_ON_START

***

#### [](#apifyenvvars-system_info_interval_millis) `ApifyEnvVars.SYSTEM_INFO_INTERVAL_MILLIS`

SYSTEM_INFO_INTERVAL_MILLIS

***

### [](#actorexitcodes) ActorExitCodes

Usual actor exit codes.

* [SUCCESS](#actorexitcodes-success)
* [ERROR\_USER\_FUNCTION\_THREW](#actorexitcodes-error\_user\_function\_threw)

***

#### [](#actorexitcodes-success) `ActorExitCodes.SUCCESS`

The actor finished successfully

***

#### [](#actorexitcodes-error_user_function_threw) `ActorExitCodes.ERROR_USER_FUNCTION_THREW`

The main function of the actor threw an Exception
