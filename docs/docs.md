# Apify SDK for Python

TODO: write docs

## API Reference

All public classes, methods and their parameters can be inspected in this API reference.

### [](#actor) Actor

Class representing an Apify Actor.

* [\_\_init\_\_()](#actor-\_\_init\_\_)

***

#### [](#actor-__init__) `Actor.__init__(config=None)`

TODO: docs.

***

#### async classmethod init()

TODO: docs.

* **Return type**

  `None`

***

#### async classmethod exit(\*, exit_code=0)

TODO: docs.

* **Return type**

  `None`

***

#### async classmethod fail(\*, exit_code=1)

TODO: docs.

* **Return type**

  `None`

***

#### async classmethod main(main_actor_coro)

TODO: docs.

* **Return type**

  `Optional`[`TypeVar`(`MainReturnType`)]

***

#### classmethod new_client(\*, token=None, api_url=None, max_retries=None, min_delay_between_retries_millis=None, timeout_secs=None)

TODO: docs.

* **Return type**

  `ApifyClientAsync`

***

#### async classmethod open_dataset(dataset_id_or_name=None)

TODO: docs.

* **Return type**

  `DatasetClientAsync`

***

#### async classmethod open_key_value_store(key_value_store_id_or_name=None)

TODO: docs.

* **Return type**

  `KeyValueStoreClientAsync`

***

#### async classmethod open_request_queue(request_queue_id_or_name=None)

TODO: docs.

* **Return type**

  `RequestQueueClientAsync`

***

#### async classmethod push_data(data)

TODO: docs.

* **Return type**

  `None`

***

#### async classmethod get_input()

TODO: docs.

* **Return type**

  `Any`

***

#### async classmethod get_value(key)

TODO: docs.

* **Return type**

  `Any`

***

#### async classmethod set_value(key, value, options=None)

TODO: docs.

* **Return type**

  `None`

***

#### classmethod on(event, listener)

TODO: docs.

* **Return type**

  `Callable`

***

#### classmethod off(event, listener)

TODO: docs.

* **Return type**

  `None`

***

#### classmethod is_at_home()

TODO: docs.

* **Return type**

  `bool`

***

#### classmethod get_env()

TODO: docs.

* **Return type**

  `Dict`

***

#### async classmethod start(actor_id, run_input=None, \*, token=None, content_type=None, build=None, memory_mbytes=None, timeout_secs=None, wait_for_finish=None, webhooks=None)

TODO: docs.

* **Return type**

  `Dict`

***

#### async classmethod abort(run_id, \*, token=None, gracefully=None)

TODO: docs.

* **Return type**

  `Dict`

***

#### async classmethod call(actor_id, run_input=None, \*, token=None, content_type=None, build=None, memory_mbytes=None, timeout_secs=None, webhooks=None, wait_secs=None)

TODO: docs.

* **Return type**

  `Optional[Dict]`

***

#### async classmethod call_task(task_id, task_input=None, \*, build=None, memory_mbytes=None, timeout_secs=None, webhooks=None, wait_secs=None, token=None)

TODO: docs.

* **Return type**

  `Optional[Dict]`

***

#### async classmethod metamorph(target_actor_id, run_input=None, \*, target_actor_build=None, content_type=None, custom_after_sleep_millis=None)

TODO: docs.

* **Return type**

  `None`

***

#### async classmethod reboot()

TODO: docs.

* **Return type**

  `None`

***

#### async classmethod add_webhook(\*, event_types, request_url, payload_template=None, ignore_ssl_errors=None, do_not_retry=None, idempotency_key=None)

TODO: docs.

* **Return type**

  `Dict`

***

#### async classmethod set_status_message(status_message)

TODO: docs.

* **Return type**

  `Dict`
