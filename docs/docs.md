# Apify SDK for Python

TODO: write docs

## API Reference

All public classes, methods and their parameters can be inspected in this API reference.

### [](#actor) Actor

Class representing an Apify Actor.

* [\_\_init\_\_()](#actor-\_\_init\_\_)

***

#### [](#actor-__init__) `Actor.__init__(config=None)`

Create an Actor instance.

* **Parameters**

  * **config** (`Configuration`, *optional*) – The actor configuration to be used. If not passed, a new Configuration instance will be created.

***

#### async classmethod init()

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

#### async classmethod exit(\*, exit_code=0, event_listeners_timeout_secs=5)

Exit the actor instance.

This stops the Actor instance.
It cancels all the intervals for regularly sending PERSIST_STATE events,
sends a final PERSIST_STATE event,
waits for all the event listeners to finish,
and stops the event manager.

* **Parameters**

  * **exit_code** (`int`, *optional*) – The exit code with which the actor should fail (defaults to 0).

  * **event_listeners_timeout_secs** (`int`, *optional*) – How long should the actor wait for actor event listeners to finish before exiting

* **Return type**

  `None`

***

#### async classmethod fail(\*, exit_code=1, _exc_type=None, _exc_value=None, _exc_traceback=None)

Fail the actor instance.

This performs all the same steps as Actor.exit(),
but it additionally sets the exit code to 1 (by default).

* **Parameters**

  * **exit_code** (`int`, *optional*) – The exit code with which the actor should fail (defaults to 1).

* **Return type**

  `None`

***

#### async classmethod main(main_actor_function)

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

#### classmethod new_client(\*, token=None, api_url=None, max_retries=None, min_delay_between_retries_millis=None, timeout_secs=None)

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

#### async classmethod open_dataset(dataset_id_or_name=None, \*, force_cloud=False)

Open a dataset.

Datasets are used to store structured data where each object stored has the same attributes,
such as online store products or real estate offers.
The actual data is stored either on the local filesystem or in the Apify cloud.

* **Parameters**

  * **dataset_id_or_name** (`str`, *optional*) – ID or name of the dataset to be opened.
  If not provided, the method returns the default dataset associated with the actor run.

  * **force_cloud** (`bool`, *optional*) – If set to True then the Apify cloud storage is always used.
  This way it is possible to combine local and cloud storage.

* **Returns**

  An instance of the Dataset class for the given ID or name.

* **Return type**

  `Dataset`

***

#### async classmethod open_key_value_store(key_value_store_id_or_name=None, \*, force_cloud=False)

Open a key-value store.

Key-value stores are used to store records or files, along with their MIME content type.
The records are stored and retrieved using a unique key.
The actual data is stored either on a local filesystem or in the Apify cloud.

* **Parameters**

  * **key_value_store_id_or_name** (`str`, *optional*) – ID or name of the key-value store to be opened.
  If not provided, the method returns the default key-value store associated with the actor run.

  * **force_cloud** (`bool`, *optional*) – If set to True then the Apify cloud storage is always used.
  This way it is possible to combine local and cloud storage.

* **Returns**

  An instance of the KeyValueStore class for the given ID or name.

* **Return type**

  `KeyValueStore`

***

#### async classmethod open_request_queue(request_queue_id_or_name=None, \*, force_cloud=False)

Open a request queue.

Request queue represents a queue of URLs to crawl, which is stored either on local filesystem or in the Apify cloud.
The queue is used for deep crawling of websites, where you start with several URLs and then
recursively follow links to other pages. The data structure supports both breadth-first
and depth-first crawling orders.

* **Parameters**

  * **request_queue_id_or_name** (`str`, *optional*) – ID or name of the request queue to be opened.
  If not provided, the method returns the default request queue associated with the actor run.

  * **force_cloud** (`bool`, *optional*) – If set to True then the Apify cloud storage is always used.
  This way it is possible to combine local and cloud storage.

* **Returns**

  An instance of the RequestQueue class for the given ID or name.

* **Return type**

  `RequestQueue`

***

#### async classmethod push_data(data)

Store an object or a list of objects to the default dataset of the current actor run.

* **Parameters**

  * **data** (`object or list of objects`, *optional*) – The data to push to the default dataset.

* **Return type**

  `None`

***

#### async classmethod get_input()

Get the actor input value from the default key-value store associated with the current actor run.

* **Return type**

  `Any`

***

#### async classmethod get_value(key)

Get a value from the default key-value store associated with the current actor run.

* **Parameters**

  * **key** (`str`) – The key of the record which to retrieve.

* **Return type**

  `Any`

***

#### async classmethod set_value(key, value, \*, content_type=None)

Set or delete a value in the default key-value store associated with the current actor run.

* **Parameters**

  * **key** (`str`) – The key of the record which to set.

  * **value** (`any`) – The value of the record which to set, or `None`, if the record should be deleted.

  * **content_type** (`str`, *optional*) – The content type which should be set to the value.

* **Return type**

  `None`

***

#### classmethod on(event_name, listener)

Add an event listener to the actor’s event manager.

The following events can be emitted:

  * ActorEventType.SYSTEM_INFO:

    Emitted every minute, the event data contains info about the resource usage of the actor.

  * ActorEventType.MIGRATING:

    Emitted when the actor running on the Apify platform is going to be migrated to another worker server soon.
    You can use it to persist the state of the actor and abort the run, to speed up the migration.

  * ActorEventType.PERSIST_STATE:

    Emitted in regular intervals (by default 60 seconds) to notify the actor that it should persist its state,
    in order to avoid repeating all work when the actor restarts.
    This event is automatically emitted together with the migrating event,
    in which case the isMigrating flag in the event data is set to True, otherwise the flag is False.
    Note that this event is provided merely for your convenience,
    you can achieve the same effect using an interval and listening for the migrating event.

  * ActorEventType.ABORTING:

    When a user aborts an actor run on the Apify platform,
    they can choose to abort it gracefully, to allow the actor some time before getting terminated.
    This graceful abort emits the aborting event, which you can use to clean up the actor state.

* **Parameters**

  * **event_name** (`ActorEventType`) – The actor event for which to listen to.

  * **listener** (`Callable`) – The function which is to be called when the event is emitted (can be async).

* **Return type**

  `Callable`

***

#### classmethod off(event_name, listener=None)

Remove a listener, or all listeners, from an actor event.

* **Parameters**

  * **event_name** (`ActorEventType`) – The actor event for which to remove listeners.

  * **listener** (`Callable`, *optional*) – The listener which is supposed to be removed. If not passed, all listeners of this event are removed.

* **Return type**

  `None`

***

#### classmethod is_at_home()

Return True when the actor is running on the Apify platform, and False otherwise (for example when running locally).

* **Return type**

  `bool`

***

#### classmethod get_env()

Return a dictionary with information parsed from all the APIFY_XXX environment variables.

For a list of all the environment variables,
see the [Actor documentation]([https://docs.apify.com/actors/development/environment-variables](https://docs.apify.com/actors/development/environment-variables)).
If some variables are not defined or are invalid, the corresponding value in the resulting dictionary will be None.

* **Return type**

  `Dict`

***

#### async classmethod start(actor_id, run_input=None, \*, token=None, content_type=None, build=None, memory_mbytes=None, timeout_secs=None, wait_for_finish=None, webhooks=None)

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

#### async classmethod abort(run_id, \*, token=None, gracefully=None)

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

#### async classmethod call(actor_id, run_input=None, \*, token=None, content_type=None, build=None, memory_mbytes=None, timeout_secs=None, webhooks=None, wait_secs=None)

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

#### async classmethod call_task(task_id, task_input=None, \*, build=None, memory_mbytes=None, timeout_secs=None, webhooks=None, wait_secs=None, token=None)

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

#### async classmethod metamorph(target_actor_id, run_input=None, \*, target_actor_build=None, content_type=None, custom_after_sleep_millis=None)

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

#### async classmethod reboot(\*, event_listeners_timeout_secs=5)

Internally reboot this actor.

The system stops the current container and starts a new one, with the same run ID and default storages.

* **Parameters**

  * **event_listeners_timeout_secs** (`int`, *optional*) – How long should the actor wait for actor event listeners to finish before exiting

* **Return type**

  `None`

***

#### async classmethod add_webhook(\*, event_types, request_url, payload_template=None, ignore_ssl_errors=None, do_not_retry=None, idempotency_key=None)

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

#### async classmethod set_status_message(status_message)

Set the status message for the current actor run.

* **Parameters**

  * **status_message** (`str`) – The status message to set to the run.

* **Returns**

  The updated actor run object

* **Return type**

  `dict`

***

#### async classmethod create_proxy_configuration(\*, password=None, groups=None, country_code=None, proxy_urls=None, new_url_function=None, actor_proxy_input=None)

Create a ProxyConfiguration object with the passed proxy configuration.

Configures connection to a proxy server with the provided options.
Proxy servers are used to prevent target websites from blocking your crawlers based on IP address rate limits or blacklists.

For more details and code examples, see the ProxyConfiguration class.

* **Parameters**

  * **password** (`str`, *optional*) – Password for the Apify Proxy. If not provided, will use os.environ[‘APIFY_PROXY_PASSWORD’], if available.

  * **groups** (`list of str`, *optional*) – Proxy groups which the Apify Proxy should use, if provided.

  * **country_code** (`str`, *optional*) – Country which the Apify Proxy should use, if provided.

  * **proxy_urls** (`list of str`, *optional*) – Custom proxy server URLs which should be rotated through.

  * **new_url_function** (`Callable`, *optional*) – Function which returns a custom proxy URL to be used.

  * **actor_proxy_input** (`dict`, *optional*) – Proxy configuration field from the actor input, if actor has such input field.

* **Returns**

  ProxyConfiguration object with the passed configuration,

    or `None`, if no proxy should be used based on the configuration.

* **Return type**

  `ProxyConfiguration`, optional
