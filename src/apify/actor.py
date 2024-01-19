from __future__ import annotations

import asyncio
import contextlib
import inspect
import os
import sys
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Awaitable, Callable, TypeVar, cast

from apify_client import ApifyClientAsync
from apify_shared.consts import ActorEnvVars, ActorEventTypes, ActorExitCodes, ApifyEnvVars, WebhookEventType
from apify_shared.utils import ignore_docs, maybe_extract_enum_member_value

from apify._crypto import decrypt_input_secrets, load_private_key
from apify._utils import (
    dualproperty,
    fetch_and_parse_env_var,
    get_cpu_usage_percent,
    get_memory_usage_bytes,
    get_system_info,
    is_running_in_ipython,
    run_func_at_interval_async,
    wrap_internal,
)
from apify.config import Configuration
from apify.consts import EVENT_LISTENERS_TIMEOUT_SECS
from apify.event_manager import EventManager
from apify.log import logger
from apify.proxy_configuration import ProxyConfiguration
from apify.storages import Dataset, KeyValueStore, RequestQueue, StorageClientManager

if TYPE_CHECKING:
    import logging
    from types import TracebackType

    from apify._memory_storage import MemoryStorageClient

T = TypeVar('T')
MainReturnType = TypeVar('MainReturnType')

# This metaclass is needed so you can do `async with Actor: ...` instead of `async with Actor() as a: ...`
# and have automatic `Actor.init()` and `Actor.exit()`


class _ActorContextManager(type):
    @staticmethod
    async def __aenter__() -> type[Actor]:
        await Actor.init()
        return Actor

    @staticmethod
    async def __aexit__(
        _exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        _exc_traceback: TracebackType | None,
    ) -> None:
        if not Actor._get_default_instance()._is_exiting:
            if exc_value:
                await Actor.fail(
                    exit_code=ActorExitCodes.ERROR_USER_FUNCTION_THREW.value,
                    exception=exc_value,
                )
            else:
                await Actor.exit()


class Actor(metaclass=_ActorContextManager):
    """The main class of the SDK, through which all the actor operations should be done."""

    _default_instance: Actor | None = None
    _apify_client: ApifyClientAsync
    _memory_storage_client: MemoryStorageClient
    _config: Configuration
    _event_manager: EventManager
    _send_system_info_interval_task: asyncio.Task | None = None
    _send_persist_state_interval_task: asyncio.Task | None = None
    _is_exiting = False
    _was_final_persist_state_emitted = False

    def __init__(self: Actor, config: Configuration | None = None) -> None:
        """Create an Actor instance.

        Note that you don't have to do this, all the methods on this class function as classmethods too,
        and that is their preferred usage.

        Args:
            config (Configuration, optional): The actor configuration to be used. If not passed, a new Configuration instance will be created.
        """
        # To have methods which work the same as classmethods and instance methods,
        # so you can do both Actor.xxx() and Actor().xxx(),
        # we need to have an `_xxx_internal` instance method which contains the actual implementation of the method,
        # and then in the instance constructor overwrite the `xxx` classmethod with the `_xxx_internal` instance method,
        # while copying the annotations, types and so on.
        self.init = wrap_internal(self._init_internal, self.init)  # type: ignore
        self.exit = wrap_internal(self._exit_internal, self.exit)  # type: ignore
        self.fail = wrap_internal(self._fail_internal, self.fail)  # type: ignore
        self.main = wrap_internal(self._main_internal, self.main)  # type: ignore
        self.new_client = wrap_internal(self._new_client_internal, self.new_client)  # type: ignore

        self.open_dataset = wrap_internal(self._open_dataset_internal, self.open_dataset)  # type: ignore
        self.open_key_value_store = wrap_internal(self._open_key_value_store_internal, self.open_key_value_store)  # type: ignore
        self.open_request_queue = wrap_internal(self._open_request_queue_internal, self.open_request_queue)  # type: ignore
        self.push_data = wrap_internal(self._push_data_internal, self.push_data)  # type: ignore
        self.get_input = wrap_internal(self._get_input_internal, self.get_input)  # type: ignore
        self.get_value = wrap_internal(self._get_value_internal, self.get_value)  # type: ignore
        self.set_value = wrap_internal(self._set_value_internal, self.set_value)  # type: ignore

        self.on = wrap_internal(self._on_internal, self.on)  # type: ignore
        self.off = wrap_internal(self._off_internal, self.off)  # type: ignore

        self.is_at_home = wrap_internal(self._is_at_home_internal, self.is_at_home)  # type: ignore
        self.get_env = wrap_internal(self._get_env_internal, self.get_env)  # type: ignore

        self.start = wrap_internal(self._start_internal, self.start)  # type: ignore
        self.call = wrap_internal(self._call_internal, self.call)  # type: ignore
        self.call_task = wrap_internal(self._call_task_internal, self.call_task)  # type: ignore
        self.abort = wrap_internal(self._abort_internal, self.abort)  # type: ignore
        self.metamorph = wrap_internal(self._metamorph_internal, self.metamorph)  # type: ignore
        self.reboot = wrap_internal(self._reboot_internal, self.reboot)  # type: ignore
        self.add_webhook = wrap_internal(self._add_webhook_internal, self.add_webhook)  # type: ignore
        self.set_status_message = wrap_internal(self._set_status_message_internal, self.set_status_message)  # type: ignore
        self.create_proxy_configuration = wrap_internal(self._create_proxy_configuration_internal, self.create_proxy_configuration)  # type: ignore

        self._config: Configuration = config or Configuration()
        self._apify_client = self.new_client()
        self._event_manager = EventManager(config=self._config)

        self._is_initialized = False

    @ignore_docs
    async def __aenter__(self: Actor) -> Actor:
        """Initialize the Actor.

        Automatically initializes the Actor instance when you use it in an `async with ...` statement.

        When you exit the `async with` block, the `Actor.exit()` method is called,
        and if any exception happens while executing the block code,
        the `Actor.fail` method is called.
        """
        await self.init()
        return self

    @ignore_docs
    async def __aexit__(
        self: Actor,
        _exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        _exc_traceback: TracebackType | None,
    ) -> None:
        """Exit the Actor, handling any exceptions properly.

        When you exit the `async with` block, the `Actor.exit()` method is called,
        and if any exception happens while executing the block code,
        the `Actor.fail` method is called.
        """
        if not self._is_exiting:
            if exc_value:
                await self.fail(
                    exit_code=ActorExitCodes.ERROR_USER_FUNCTION_THREW.value,
                    exception=exc_value,
                )
            else:
                await self.exit()

    @classmethod
    def _get_default_instance(cls: type[Actor]) -> Actor:
        if not cls._default_instance:
            cls._default_instance = cls(config=Configuration.get_global_configuration())

        return cls._default_instance

    @dualproperty
    def apify_client(self_or_cls: type[Actor] | Actor) -> ApifyClientAsync:  # noqa: N805
        """The ApifyClientAsync instance the Actor instance uses."""
        if isinstance(self_or_cls, type):
            return self_or_cls._get_default_instance()._apify_client
        return self_or_cls._apify_client

    @dualproperty
    def config(self_or_cls: type[Actor] | Actor) -> Configuration:  # noqa: N805
        """The Configuration instance the Actor instance uses."""
        if isinstance(self_or_cls, type):
            return self_or_cls._get_default_instance()._config
        return self_or_cls._config

    @dualproperty
    def event_manager(self_or_cls: type[Actor] | Actor) -> EventManager:  # noqa: N805
        """The EventManager instance the Actor instance uses."""
        if isinstance(self_or_cls, type):
            return self_or_cls._get_default_instance()._event_manager

        return self_or_cls._event_manager

    @dualproperty
    def log(_self_or_cls: type[Actor] | Actor) -> logging.Logger:  # noqa: N805
        """The logging.Logger instance the Actor uses."""
        return logger

    def _raise_if_not_initialized(self: Actor) -> None:
        if not self._is_initialized:
            raise RuntimeError('The actor was not initialized!')

    @classmethod
    async def init(cls: type[Actor]) -> None:
        """Initialize the actor instance.

        This initializes the Actor instance.
        It configures the right storage client based on whether the actor is running locally or on the Apify platform,
        it initializes the event manager for processing actor events,
        and starts an interval for regularly sending `PERSIST_STATE` events,
        so that the actor can regularly persist its state in response to these events.

        This method should be called immediately before performing any additional actor actions,
        and it should be called only once.
        """
        return await cls._get_default_instance().init()

    async def _init_internal(self: Actor) -> None:
        if self._is_initialized:
            raise RuntimeError('The actor was already initialized!')

        self._is_exiting = False
        self._was_final_persist_state_emitted = False

        self.log.info('Initializing actor...')
        self.log.info('System info', extra=get_system_info())

        # TODO: Print outdated SDK version warning (we need a new env var for this)
        # https://github.com/apify/apify-sdk-python/issues/146

        StorageClientManager.set_config(self._config)
        if self._config.token:
            StorageClientManager.set_cloud_client(self._apify_client)

        await self._event_manager.init()

        self._send_persist_state_interval_task = asyncio.create_task(
            run_func_at_interval_async(
                lambda: self._event_manager.emit(ActorEventTypes.PERSIST_STATE, {'isMigrating': False}),
                self._config.persist_state_interval_millis / 1000,
            ),
        )

        if not self.is_at_home():
            self._send_system_info_interval_task = asyncio.create_task(
                run_func_at_interval_async(
                    lambda: self._event_manager.emit(ActorEventTypes.SYSTEM_INFO, self.get_system_info()),
                    self._config.system_info_interval_millis / 1000,
                ),
            )

        self._event_manager.on(ActorEventTypes.MIGRATING, self._respond_to_migrating_event)

        # The CPU usage is calculated as an average between two last calls to psutil
        # We need to make a first, dummy call, so the next calls have something to compare itself agains
        get_cpu_usage_percent()

        self._is_initialized = True

    def get_system_info(self: Actor) -> dict:
        """Get the current system info."""
        cpu_usage_percent = get_cpu_usage_percent()
        memory_usage_bytes = get_memory_usage_bytes()
        # This is in camel case to be compatible with the events from the platform
        result = {
            'createdAt': datetime.now(timezone.utc),
            'cpuCurrentUsage': cpu_usage_percent,
            'memCurrentBytes': memory_usage_bytes,
        }
        if self._config.max_used_cpu_ratio:
            result['isCpuOverloaded'] = cpu_usage_percent > 100 * self._config.max_used_cpu_ratio

        return result

    async def _respond_to_migrating_event(self: Actor, _event_data: Any) -> None:
        # Don't emit any more regular persist state events
        if self._send_persist_state_interval_task and not self._send_persist_state_interval_task.cancelled():
            self._send_persist_state_interval_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._send_persist_state_interval_task

        self._event_manager.emit(ActorEventTypes.PERSIST_STATE, {'isMigrating': True})
        self._was_final_persist_state_emitted = True

    async def _cancel_event_emitting_intervals(self: Actor) -> None:
        if self._send_persist_state_interval_task and not self._send_persist_state_interval_task.cancelled():
            self._send_persist_state_interval_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._send_persist_state_interval_task

        if self._send_system_info_interval_task and not self._send_system_info_interval_task.cancelled():
            self._send_system_info_interval_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._send_system_info_interval_task

    @classmethod
    async def exit(
        cls: type[Actor],
        *,
        exit_code: int = 0,
        event_listeners_timeout_secs: float | None = EVENT_LISTENERS_TIMEOUT_SECS,
        status_message: str | None = None,
    ) -> None:
        """Exit the actor instance.

        This stops the Actor instance.
        It cancels all the intervals for regularly sending `PERSIST_STATE` events,
        sends a final `PERSIST_STATE` event,
        waits for all the event listeners to finish,
        and stops the event manager.

        Args:
            exit_code (int, optional): The exit code with which the actor should fail (defaults to `0`).
            event_listeners_timeout_secs (float, optional): How long should the actor wait for actor event listeners to finish before exiting.
            status_message (str, optional): The final status message that the actor should display.
        """
        return await cls._get_default_instance().exit(
            exit_code=exit_code,
            event_listeners_timeout_secs=event_listeners_timeout_secs,
            status_message=status_message,
        )

    async def _exit_internal(
        self: Actor,
        *,
        exit_code: int = 0,
        event_listeners_timeout_secs: float | None = EVENT_LISTENERS_TIMEOUT_SECS,
        status_message: str | None = None,
    ) -> None:
        self._raise_if_not_initialized()

        self._is_exiting = True

        exit_code = maybe_extract_enum_member_value(exit_code)

        self.log.info('Exiting actor', extra={'exit_code': exit_code})

        await self._cancel_event_emitting_intervals()

        # Send final persist state event
        if not self._was_final_persist_state_emitted:
            self._event_manager.emit(ActorEventTypes.PERSIST_STATE, {'isMigrating': False})
            self._was_final_persist_state_emitted = True

        if status_message is not None:
            await self.set_status_message(status_message, is_terminal=True)

        # Sleep for a bit so that the listeners have a chance to trigger
        await asyncio.sleep(0.1)

        await self._event_manager.close(event_listeners_timeout_secs=event_listeners_timeout_secs)

        self._is_initialized = False

        if is_running_in_ipython():
            self.log.debug(f'Not calling sys.exit({exit_code}) because actor is running in IPython')
        elif os.getenv('PYTEST_CURRENT_TEST', default=False):  # noqa: PLW1508
            self.log.debug(f'Not calling sys.exit({exit_code}) because actor is running in an unit test')
        elif hasattr(asyncio, '_nest_patched'):
            self.log.debug(f'Not calling sys.exit({exit_code}) because actor is running in a nested event loop')
        else:
            sys.exit(exit_code)

    @classmethod
    async def fail(
        cls: type[Actor],
        *,
        exit_code: int = 1,
        exception: BaseException | None = None,
        status_message: str | None = None,
    ) -> None:
        """Fail the actor instance.

        This performs all the same steps as Actor.exit(),
        but it additionally sets the exit code to `1` (by default).

        Args:
            exit_code (int, optional): The exit code with which the actor should fail (defaults to `1`).
            exception (BaseException, optional): The exception with which the actor failed.
            status_message (str, optional): The final status message that the actor should display.
        """
        return await cls._get_default_instance().fail(
            exit_code=exit_code,
            exception=exception,
            status_message=status_message,
        )

    async def _fail_internal(
        self: Actor,
        *,
        exit_code: int = 1,
        exception: BaseException | None = None,
        status_message: str | None = None,
    ) -> None:
        self._raise_if_not_initialized()

        # In IPython, we don't run `sys.exit()` during actor exits,
        # so the exception traceback will be printed on its own
        if exception and not is_running_in_ipython():
            self.log.exception('Actor failed with an exception', exc_info=exception)

        await self.exit(exit_code=exit_code, status_message=status_message)

    @classmethod
    async def main(cls: type[Actor], main_actor_function: Callable[[], MainReturnType]) -> MainReturnType | None:
        """Initialize the actor, run the passed function and finish the actor cleanly.

        **The `Actor.main()` function is optional** and is provided merely for your convenience.
        It is mainly useful when you're running your code as an actor on the [Apify platform](https://apify.com/actors).

        The `Actor.main()` function performs the following actions:

        - When running on the Apify platform (i.e. `APIFY_IS_AT_HOME` environment variable is set),
          it sets up a connection to listen for platform events.
          For example, to get a notification about an imminent migration to another server.
        - It invokes the user function passed as the `main_actor_function` parameter.
        - If the user function was an async function, it awaits it.
        - If the user function throws an exception or some other error is encountered,
          it prints error details to console so that they are stored to the log,
          and finishes the actor cleanly.
        - Finally, it exits the Python process, with zero exit code on success and non-zero on errors.

        Args:
            main_actor_function (Callable): The user function which should be run in the actor
        """
        return await cls._get_default_instance().main(
            main_actor_function=main_actor_function,
        )

    async def _main_internal(self: Actor, main_actor_function: Callable[[], MainReturnType]) -> MainReturnType | None:
        if not inspect.isfunction(main_actor_function):
            raise TypeError(f'First argument passed to Actor.main() must be a function, but instead it was {type(main_actor_function)}')

        await self.init()
        try:
            if inspect.iscoroutinefunction(main_actor_function):
                res = await main_actor_function()
            else:
                res = main_actor_function()
            await self.exit()
            return cast(MainReturnType, res)
        except Exception as exc:
            await self.fail(
                exit_code=ActorExitCodes.ERROR_USER_FUNCTION_THREW.value,
                exception=exc,
            )
        return None

    @classmethod
    def new_client(
        cls: type[Actor],
        *,
        token: str | None = None,
        api_url: str | None = None,
        max_retries: int | None = None,
        min_delay_between_retries_millis: int | None = None,
        timeout_secs: int | None = None,
    ) -> ApifyClientAsync:
        """Return a new instance of the Apify API client.

        The `ApifyClientAsync` class is provided by the [apify-client](https://github.com/apify/apify-client-python) package,
        and it is automatically configured using the `APIFY_API_BASE_URL` and `APIFY_TOKEN` environment variables.

        You can override the token via the available options.
        That's useful if you want to use the client as a different Apify user than the SDK internals are using.

        Args:
            token (str, optional): The Apify API token
            api_url (str, optional): The URL of the Apify API server to which to connect to. Defaults to https://api.apify.com
            max_retries (int, optional): How many times to retry a failed request at most
            min_delay_between_retries_millis (int, optional): How long will the client wait between retrying requests
                (increases exponentially from this value)
            timeout_secs (int, optional): The socket timeout of the HTTP requests sent to the Apify API
        """
        return cls._get_default_instance().new_client(
            token=token,
            api_url=api_url,
            max_retries=max_retries,
            min_delay_between_retries_millis=min_delay_between_retries_millis,
            timeout_secs=timeout_secs,
        )

    def _new_client_internal(
        self: Actor,
        *,
        token: str | None = None,
        api_url: str | None = None,
        max_retries: int | None = None,
        min_delay_between_retries_millis: int | None = None,
        timeout_secs: int | None = None,
    ) -> ApifyClientAsync:
        token = token or self._config.token
        api_url = api_url or self._config.api_base_url
        return ApifyClientAsync(
            token=token,
            api_url=api_url,
            max_retries=max_retries,
            min_delay_between_retries_millis=min_delay_between_retries_millis,
            timeout_secs=timeout_secs,
        )

    def _get_storage_client(self: Actor, force_cloud: bool) -> ApifyClientAsync | None:  # noqa: FBT001
        return self._apify_client if force_cloud else None

    @classmethod
    async def open_dataset(
        cls: type[Actor],
        *,
        id: str | None = None,  # noqa: A002
        name: str | None = None,
        force_cloud: bool = False,
    ) -> Dataset:
        """Open a dataset.

        Datasets are used to store structured data where each object stored has the same attributes,
        such as online store products or real estate offers.
        The actual data is stored either on the local filesystem or in the Apify cloud.

        Args:
            id (str, optional): ID of the dataset to be opened.
                If neither `id` nor `name` are provided, the method returns the default dataset associated with the actor run.
            name (str, optional): Name of the dataset to be opened.
                If neither `id` nor `name` are provided, the method returns the default dataset associated with the actor run.
            force_cloud (bool, optional): If set to `True` then the Apify cloud storage is always used.
                This way it is possible to combine local and cloud storage.

        Returns:
            Dataset: An instance of the `Dataset` class for the given ID or name.

        """
        return await cls._get_default_instance().open_dataset(id=id, name=name, force_cloud=force_cloud)

    async def _open_dataset_internal(
        self: Actor,
        *,
        id: str | None = None,  # noqa: A002
        name: str | None = None,
        force_cloud: bool = False,
    ) -> Dataset:
        self._raise_if_not_initialized()

        return await Dataset.open(id=id, name=name, force_cloud=force_cloud, config=self._config)

    @classmethod
    async def open_key_value_store(
        cls: type[Actor],
        *,
        id: str | None = None,  # noqa: A002
        name: str | None = None,
        force_cloud: bool = False,
    ) -> KeyValueStore:
        """Open a key-value store.

        Key-value stores are used to store records or files, along with their MIME content type.
        The records are stored and retrieved using a unique key.
        The actual data is stored either on a local filesystem or in the Apify cloud.

        Args:
            id (str, optional): ID of the key-value store to be opened.
                If neither `id` nor `name` are provided, the method returns the default key-value store associated with the actor run.
            name (str, optional): Name of the key-value store to be opened.
                If neither `id` nor `name` are provided, the method returns the default key-value store associated with the actor run.
            force_cloud (bool, optional): If set to `True` then the Apify cloud storage is always used.
                This way it is possible to combine local and cloud storage.

        Returns:
            KeyValueStore: An instance of the `KeyValueStore` class for the given ID or name.
        """
        return await cls._get_default_instance().open_key_value_store(id=id, name=name, force_cloud=force_cloud)

    async def _open_key_value_store_internal(
        self: Actor,
        *,
        id: str | None = None,  # noqa: A002
        name: str | None = None,
        force_cloud: bool = False,
    ) -> KeyValueStore:
        self._raise_if_not_initialized()

        return await KeyValueStore.open(id=id, name=name, force_cloud=force_cloud, config=self._config)

    @classmethod
    async def open_request_queue(
        cls: type[Actor],
        *,
        id: str | None = None,  # noqa: A002
        name: str | None = None,
        force_cloud: bool = False,
    ) -> RequestQueue:
        """Open a request queue.

        Request queue represents a queue of URLs to crawl, which is stored either on local filesystem or in the Apify cloud.
        The queue is used for deep crawling of websites, where you start with several URLs and then
        recursively follow links to other pages. The data structure supports both breadth-first
        and depth-first crawling orders.

        Args:
            id (str, optional): ID of the request queue to be opened.
                If neither `id` nor `name` are provided, the method returns the default request queue associated with the actor run.
            name (str, optional): Name of the request queue to be opened.
                If neither `id` nor `name` are provided, the method returns the default request queue associated with the actor run.
            force_cloud (bool, optional): If set to `True` then the Apify cloud storage is always used.
                This way it is possible to combine local and cloud storage.

        Returns:
            RequestQueue: An instance of the `RequestQueue` class for the given ID or name.
        """
        return await cls._get_default_instance().open_request_queue(id=id, name=name, force_cloud=force_cloud)

    async def _open_request_queue_internal(
        self: Actor,
        *,
        id: str | None = None,  # noqa: A002
        name: str | None = None,
        force_cloud: bool = False,
    ) -> RequestQueue:
        self._raise_if_not_initialized()

        return await RequestQueue.open(id=id, name=name, force_cloud=force_cloud, config=self._config)

    @classmethod
    async def push_data(cls: type[Actor], data: Any) -> None:
        """Store an object or a list of objects to the default dataset of the current actor run.

        Args:
            data (object or list of objects, optional): The data to push to the default dataset.
        """
        return await cls._get_default_instance().push_data(data=data)

    async def _push_data_internal(self: Actor, data: Any) -> None:
        self._raise_if_not_initialized()

        if not data:
            return

        dataset = await self.open_dataset()
        await dataset.push_data(data)

    @classmethod
    async def get_input(cls: type[Actor]) -> Any:
        """Get the actor input value from the default key-value store associated with the current actor run."""
        return await cls._get_default_instance().get_input()

    async def _get_input_internal(self: Actor) -> Any:
        self._raise_if_not_initialized()

        input_value = await self.get_value(self._config.input_key)
        input_secrets_private_key = self._config.input_secrets_private_key_file
        input_secrets_key_passphrase = self._config.input_secrets_private_key_passphrase
        if input_secrets_private_key and input_secrets_key_passphrase:
            private_key = load_private_key(
                input_secrets_private_key,
                input_secrets_key_passphrase,
            )
            input_value = decrypt_input_secrets(private_key, input_value)

        return input_value

    @classmethod
    async def get_value(cls: type[Actor], key: str, default_value: Any = None) -> Any:
        """Get a value from the default key-value store associated with the current actor run.

        Args:
            key (str): The key of the record which to retrieve.
            default_value (Any, optional): Default value returned in case the record does not exist.
        """
        return await cls._get_default_instance().get_value(key=key, default_value=default_value)

    async def _get_value_internal(self: Actor, key: str, default_value: Any = None) -> Any:
        self._raise_if_not_initialized()

        key_value_store = await self.open_key_value_store()
        return await key_value_store.get_value(key, default_value)

    @classmethod
    async def set_value(
        cls: type[Actor],
        key: str,
        value: Any,
        *,
        content_type: str | None = None,
    ) -> None:
        """Set or delete a value in the default key-value store associated with the current actor run.

        Args:
            key (str): The key of the record which to set.
            value (any): The value of the record which to set, or None, if the record should be deleted.
            content_type (str, optional): The content type which should be set to the value.
        """
        return await cls._get_default_instance().set_value(
            key=key,
            value=value,
            content_type=content_type,
        )

    async def _set_value_internal(
        self: Actor,
        key: str,
        value: Any,
        *,
        content_type: str | None = None,
    ) -> None:
        self._raise_if_not_initialized()

        key_value_store = await self.open_key_value_store()
        return await key_value_store.set_value(key, value, content_type=content_type)

    @classmethod
    def on(cls: type[Actor], event_name: ActorEventTypes, listener: Callable) -> Callable:
        """Add an event listener to the actor's event manager.

        The following events can be emitted:
         - `ActorEventTypes.SYSTEM_INFO`:
            Emitted every minute, the event data contains info about the resource usage of the actor.
         - `ActorEventTypes.MIGRATING`:
            Emitted when the actor running on the Apify platform is going to be migrated to another worker server soon.
            You can use it to persist the state of the actor and gracefully stop your in-progress tasks,
            so that they are not interrupted by the migration..
         - `ActorEventTypes.PERSIST_STATE`:
            Emitted in regular intervals (by default 60 seconds) to notify the actor that it should persist its state,
            in order to avoid repeating all work when the actor restarts.
            This event is automatically emitted together with the migrating event,
            in which case the `isMigrating` flag in the event data is set to True, otherwise the flag is False.
            Note that this event is provided merely for your convenience,
            you can achieve the same effect using an interval and listening for the migrating event.
         - `ActorEventTypes.ABORTING`:
            When a user aborts an actor run on the Apify platform,
            they can choose to abort it gracefully, to allow the actor some time before getting terminated.
            This graceful abort emits the aborting event, which you can use to clean up the actor state.

        Args:
            event_name (ActorEventTypes): The actor event for which to listen to.
            listener (Callable): The function which is to be called when the event is emitted (can be async).
        """
        return cls._get_default_instance().on(event_name, listener)

    def _on_internal(self: Actor, event_name: ActorEventTypes, listener: Callable) -> Callable:
        self._raise_if_not_initialized()

        return self._event_manager.on(event_name, listener)

    @classmethod
    def off(cls: type[Actor], event_name: ActorEventTypes, listener: Callable | None = None) -> None:
        """Remove a listener, or all listeners, from an actor event.

        Args:
            event_name (ActorEventTypes): The actor event for which to remove listeners.
            listener (Callable, optional): The listener which is supposed to be removed. If not passed, all listeners of this event are removed.
        """
        return cls._get_default_instance().off(event_name, listener)

    def _off_internal(self: Actor, event_name: ActorEventTypes, listener: Callable | None = None) -> None:
        self._raise_if_not_initialized()

        return self._event_manager.off(event_name, listener)

    @classmethod
    def is_at_home(cls: type[Actor]) -> bool:
        """Return `True` when the actor is running on the Apify platform, and `False` otherwise (for example when running locally)."""
        return cls._get_default_instance().is_at_home()

    def _is_at_home_internal(self: Actor) -> bool:
        return self._config.is_at_home

    @classmethod
    def get_env(cls: type[Actor]) -> dict:
        """Return a dictionary with information parsed from all the `APIFY_XXX` environment variables.

        For a list of all the environment variables,
        see the [Actor documentation](https://docs.apify.com/actors/development/environment-variables).
        If some variables are not defined or are invalid, the corresponding value in the resulting dictionary will be None.
        """
        return cls._get_default_instance().get_env()

    def _get_env_internal(self: Actor) -> dict:
        self._raise_if_not_initialized()

        return {env_var.name.lower(): fetch_and_parse_env_var(env_var) for env_var in [*ActorEnvVars, *ApifyEnvVars]}

    @classmethod
    async def start(
        cls: type[Actor],
        actor_id: str,
        run_input: Any = None,
        *,
        token: str | None = None,
        content_type: str | None = None,
        build: str | None = None,
        memory_mbytes: int | None = None,
        timeout_secs: int | None = None,
        wait_for_finish: int | None = None,
        webhooks: list[dict] | None = None,
    ) -> dict:
        """Run an actor on the Apify platform.

        Unlike `Actor.call`, this method just starts the run without waiting for finish.

        Args:
            actor_id (str): The ID of the actor to be run.
            run_input (Any, optional): The input to pass to the actor run.
            token (str, optional): The Apify API token to use for this request (defaults to the `APIFY_TOKEN` environment variable).
            content_type (str, optional): The content type of the input.
            build (str, optional): Specifies the actor build to run. It can be either a build tag or build number.
                                   By default, the run uses the build specified in the default run configuration for the actor (typically latest).
            memory_mbytes (int, optional): Memory limit for the run, in megabytes.
                                           By default, the run uses a memory limit specified in the default run configuration for the actor.
            timeout_secs (int, optional): Optional timeout for the run, in seconds.
                                          By default, the run uses timeout specified in the default run configuration for the actor.
            wait_for_finish (int, optional): The maximum number of seconds the server waits for the run to finish.
                                               By default, it is 0, the maximum value is 300.
            webhooks (list of dict, optional): Optional ad-hoc webhooks (https://docs.apify.com/webhooks/ad-hoc-webhooks)
                                               associated with the actor run which can be used to receive a notification,
                                               e.g. when the actor finished or failed.
                                               If you already have a webhook set up for the actor or task, you do not have to add it again here.
                                               Each webhook is represented by a dictionary containing these items:
                                               * ``event_types``: list of ``WebhookEventType`` values which trigger the webhook
                                               * ``request_url``: URL to which to send the webhook HTTP request
                                               * ``payload_template`` (optional): Optional template for the request payload

        Returns:
            dict: Info about the started actor run
        """
        return await cls._get_default_instance().start(
            actor_id=actor_id,
            run_input=run_input,
            token=token,
            content_type=content_type,
            build=build,
            memory_mbytes=memory_mbytes,
            timeout_secs=timeout_secs,
            wait_for_finish=wait_for_finish,
            webhooks=webhooks,
        )

    async def _start_internal(
        self: Actor,
        actor_id: str,
        run_input: Any = None,
        *,
        token: str | None = None,
        content_type: str | None = None,
        build: str | None = None,
        memory_mbytes: int | None = None,
        timeout_secs: int | None = None,
        wait_for_finish: int | None = None,
        webhooks: list[dict] | None = None,
    ) -> dict:
        self._raise_if_not_initialized()

        client = self.new_client(token=token) if token else self._apify_client

        return await client.actor(actor_id).start(
            run_input=run_input,
            content_type=content_type,
            build=build,
            memory_mbytes=memory_mbytes,
            timeout_secs=timeout_secs,
            wait_for_finish=wait_for_finish,
            webhooks=webhooks,
        )

    @classmethod
    async def abort(
        cls: type[Actor],
        run_id: str,
        *,
        token: str | None = None,
        gracefully: bool | None = None,
    ) -> dict:
        """Abort given actor run on the Apify platform using the current user account (determined by the `APIFY_TOKEN` environment variable).

        Args:
            run_id (str): The ID of the actor run to be aborted.
            token (str, optional): The Apify API token to use for this request (defaults to the `APIFY_TOKEN` environment variable).
            gracefully (bool, optional): If True, the actor run will abort gracefully.
                It will send ``aborting`` and ``persistStates`` events into the run and force-stop the run after 30 seconds.
                It is helpful in cases where you plan to resurrect the run later.

        Returns:
            dict: Info about the aborted actor run
        """
        return await cls._get_default_instance().abort(
            run_id=run_id,
            token=token,
            gracefully=gracefully,
        )

    async def _abort_internal(
        self: Actor,
        run_id: str,
        *,
        token: str | None = None,
        status_message: str | None = None,
        gracefully: bool | None = None,
    ) -> dict:
        self._raise_if_not_initialized()

        client = self.new_client(token=token) if token else self._apify_client

        if status_message:
            await client.run(run_id).update(status_message=status_message)

        return await client.run(run_id).abort(gracefully=gracefully)

    @classmethod
    async def call(
        cls: type[Actor],
        actor_id: str,
        run_input: Any = None,
        *,
        token: str | None = None,
        content_type: str | None = None,
        build: str | None = None,
        memory_mbytes: int | None = None,
        timeout_secs: int | None = None,
        webhooks: list[dict] | None = None,
        wait_secs: int | None = None,
    ) -> dict | None:
        """Start an actor on the Apify Platform and wait for it to finish before returning.

        It waits indefinitely, unless the wait_secs argument is provided.

        Args:
            actor_id (str): The ID of the actor to be run.
            run_input (Any, optional): The input to pass to the actor run.
            token (str, optional): The Apify API token to use for this request (defaults to the `APIFY_TOKEN` environment variable).
            content_type (str, optional): The content type of the input.
            build (str, optional): Specifies the actor build to run. It can be either a build tag or build number.
                                   By default, the run uses the build specified in the default run configuration for the actor (typically latest).
            memory_mbytes (int, optional): Memory limit for the run, in megabytes.
                                           By default, the run uses a memory limit specified in the default run configuration for the actor.
            timeout_secs (int, optional): Optional timeout for the run, in seconds.
                                          By default, the run uses timeout specified in the default run configuration for the actor.
            webhooks (list, optional): Optional webhooks (https://docs.apify.com/webhooks) associated with the actor run,
                                       which can be used to receive a notification, e.g. when the actor finished or failed.
                                       If you already have a webhook set up for the actor, you do not have to add it again here.
            wait_secs (int, optional): The maximum number of seconds the server waits for the run to finish. If not provided, waits indefinitely.

        Returns:
            dict: Info about the started actor run
        """
        return await cls._get_default_instance().call(
            actor_id=actor_id,
            token=token,
            run_input=run_input,
            content_type=content_type,
            build=build,
            memory_mbytes=memory_mbytes,
            timeout_secs=timeout_secs,
            webhooks=webhooks,
            wait_secs=wait_secs,
        )

    async def _call_internal(
        self: Actor,
        actor_id: str,
        run_input: Any = None,
        *,
        token: str | None = None,
        content_type: str | None = None,
        build: str | None = None,
        memory_mbytes: int | None = None,
        timeout_secs: int | None = None,
        webhooks: list[dict] | None = None,
        wait_secs: int | None = None,
    ) -> dict | None:
        self._raise_if_not_initialized()

        client = self.new_client(token=token) if token else self._apify_client

        return await client.actor(actor_id).call(
            run_input=run_input,
            content_type=content_type,
            build=build,
            memory_mbytes=memory_mbytes,
            timeout_secs=timeout_secs,
            webhooks=webhooks,
            wait_secs=wait_secs,
        )

    @classmethod
    async def call_task(
        cls: type[Actor],
        task_id: str,
        task_input: dict | None = None,
        *,
        build: str | None = None,
        memory_mbytes: int | None = None,
        timeout_secs: int | None = None,
        webhooks: list[dict] | None = None,
        wait_secs: int | None = None,
        token: str | None = None,
    ) -> dict | None:
        """Start an actor task on the Apify Platform and wait for it to finish before returning.

        It waits indefinitely, unless the wait_secs argument is provided.

        Note that an actor task is a saved input configuration and options for an actor.
        If you want to run an actor directly rather than an actor task, please use the `Actor.call`

        Args:
            task_id (str): The ID of the actor to be run.
            task_input (Any, optional): Overrides the input to pass to the actor run.
            token (str, optional): The Apify API token to use for this request (defaults to the `APIFY_TOKEN` environment variable).
            content_type (str, optional): The content type of the input.
            build (str, optional): Specifies the actor build to run. It can be either a build tag or build number.
                                   By default, the run uses the build specified in the default run configuration for the actor (typically latest).
            memory_mbytes (int, optional): Memory limit for the run, in megabytes.
                                           By default, the run uses a memory limit specified in the default run configuration for the actor.
            timeout_secs (int, optional): Optional timeout for the run, in seconds.
                                          By default, the run uses timeout specified in the default run configuration for the actor.
            webhooks (list, optional): Optional webhooks (https://docs.apify.com/webhooks) associated with the actor run,
                                       which can be used to receive a notification, e.g. when the actor finished or failed.
                                       If you already have a webhook set up for the actor, you do not have to add it again here.
            wait_secs (int, optional): The maximum number of seconds the server waits for the run to finish. If not provided, waits indefinitely.

        Returns:
            dict: Info about the started actor run
        """
        return await cls._get_default_instance().call_task(
            task_id=task_id,
            task_input=task_input,
            token=token,
            build=build,
            memory_mbytes=memory_mbytes,
            timeout_secs=timeout_secs,
            webhooks=webhooks,
            wait_secs=wait_secs,
        )

    async def _call_task_internal(
        self: Actor,
        task_id: str,
        task_input: dict | None = None,
        *,
        build: str | None = None,
        memory_mbytes: int | None = None,
        timeout_secs: int | None = None,
        webhooks: list[dict] | None = None,
        wait_secs: int | None = None,
        token: str | None = None,
    ) -> dict | None:
        self._raise_if_not_initialized()

        client = self.new_client(token=token) if token else self._apify_client

        return await client.task(task_id).call(
            task_input=task_input,
            build=build,
            memory_mbytes=memory_mbytes,
            timeout_secs=timeout_secs,
            webhooks=webhooks,
            wait_secs=wait_secs,
        )

    @classmethod
    async def metamorph(
        cls: type[Actor],
        target_actor_id: str,
        run_input: Any = None,
        *,
        target_actor_build: str | None = None,
        content_type: str | None = None,
        custom_after_sleep_millis: int | None = None,
    ) -> None:
        """Transform this actor run to an actor run of a different actor.

        The platform stops the current actor container and starts a new container with the new actor instead.
        All the default storages are preserved,
        and the new input is stored under the `INPUT-METAMORPH-1` key in the same default key-value store.

        Args:
            target_actor_id (str): ID of the target actor that the run should be transformed into
            run_input (Any, optional): The input to pass to the new run.
            target_actor_build (str, optional): The build of the target actor. It can be either a build tag or build number.
                By default, the run uses the build specified in the default run configuration for the target actor (typically the latest build).
            content_type (str, optional): The content type of the input.
            custom_after_sleep_millis (int, optional): How long to sleep for after the metamorph, to wait for the container to be stopped.

        Returns:
            dict: The actor run data.
        """
        return await cls._get_default_instance().metamorph(
            target_actor_id=target_actor_id,
            target_actor_build=target_actor_build,
            run_input=run_input,
            content_type=content_type,
            custom_after_sleep_millis=custom_after_sleep_millis,
        )

    async def _metamorph_internal(
        self: Actor,
        target_actor_id: str,
        run_input: Any = None,
        *,
        target_actor_build: str | None = None,
        content_type: str | None = None,
        custom_after_sleep_millis: int | None = None,
    ) -> None:
        self._raise_if_not_initialized()

        if not self.is_at_home():
            self.log.error('Actor.metamorph() is only supported when running on the Apify platform.')
            return

        if not custom_after_sleep_millis:
            custom_after_sleep_millis = self._config.metamorph_after_sleep_millis

        # If is_at_home() is True, config.actor_run_id is always set
        assert self._config.actor_run_id is not None  # noqa: S101

        await self._apify_client.run(self._config.actor_run_id).metamorph(
            target_actor_id=target_actor_id,
            run_input=run_input,
            target_actor_build=target_actor_build,
            content_type=content_type,
        )

        if custom_after_sleep_millis:
            await asyncio.sleep(custom_after_sleep_millis / 1000)

    @classmethod
    async def reboot(
        cls: type[Actor],
        *,
        event_listeners_timeout_secs: int | None = EVENT_LISTENERS_TIMEOUT_SECS,
        custom_after_sleep_millis: int | None = None,
    ) -> None:
        """Internally reboot this actor.

        The system stops the current container and starts a new one, with the same run ID and default storages.

        Args:
            event_listeners_timeout_secs (int, optional): How long should the actor wait for actor event listeners to finish before exiting
            custom_after_sleep_millis (int, optional): How long to sleep for after the reboot, to wait for the container to be stopped.
        """
        return await cls._get_default_instance().reboot(
            event_listeners_timeout_secs=event_listeners_timeout_secs,
            custom_after_sleep_millis=custom_after_sleep_millis,
        )

    async def _reboot_internal(
        self: Actor,
        *,
        event_listeners_timeout_secs: int | None = EVENT_LISTENERS_TIMEOUT_SECS,
        custom_after_sleep_millis: int | None = None,
    ) -> None:
        self._raise_if_not_initialized()

        if not self.is_at_home():
            self.log.error('Actor.reboot() is only supported when running on the Apify platform.')
            return

        if not custom_after_sleep_millis:
            custom_after_sleep_millis = self._config.metamorph_after_sleep_millis

        await self._cancel_event_emitting_intervals()

        self._event_manager.emit(ActorEventTypes.PERSIST_STATE, {'isMigrating': True})
        self._was_final_persist_state_emitted = True

        await self._event_manager.close(event_listeners_timeout_secs=event_listeners_timeout_secs)

        assert self._config.actor_run_id is not None  # noqa: S101
        await self._apify_client.run(self._config.actor_run_id).reboot()

        if custom_after_sleep_millis:
            await asyncio.sleep(custom_after_sleep_millis / 1000)

    @classmethod
    async def add_webhook(
        cls: type[Actor],
        *,
        event_types: list[WebhookEventType],
        request_url: str,
        payload_template: str | None = None,
        ignore_ssl_errors: bool | None = None,
        do_not_retry: bool | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        """Create an ad-hoc webhook for the current actor run.

        This webhook lets you receive a notification when the actor run finished or failed.

        Note that webhooks are only supported for actors running on the Apify platform.
        When running the actor locally, the function will print a warning and have no effect.

        For more information about Apify actor webhooks, please see the [documentation](https://docs.apify.com/webhooks).

        Args:
            event_types (list of WebhookEventType): List of event types that should trigger the webhook. At least one is required.
            request_url (str): URL that will be invoked once the webhook is triggered.
            payload_template (str, optional): Specification of the payload that will be sent to request_url
            ignore_ssl_errors (bool, optional): Whether the webhook should ignore SSL errors returned by request_url
            do_not_retry (bool, optional): Whether the webhook should retry sending the payload to request_url upon
                                           failure.
            idempotency_key (str, optional): A unique identifier of a webhook. You can use it to ensure that you won't
                                             create the same webhook multiple times.

        Returns:
            dict: The created webhook
        """
        return await cls._get_default_instance().add_webhook(
            event_types=event_types,
            request_url=request_url,
            payload_template=payload_template,
            ignore_ssl_errors=ignore_ssl_errors,
            do_not_retry=do_not_retry,
            idempotency_key=idempotency_key,
        )

    async def _add_webhook_internal(
        self: Actor,
        *,
        event_types: list[WebhookEventType],
        request_url: str,
        payload_template: str | None = None,
        ignore_ssl_errors: bool | None = None,
        do_not_retry: bool | None = None,
        idempotency_key: str | None = None,
    ) -> dict | None:
        self._raise_if_not_initialized()

        if not self.is_at_home():
            self.log.error('Actor.add_webhook() is only supported when running on the Apify platform.')
            return None

        # If is_at_home() is True, config.actor_run_id is always set
        assert self._config.actor_run_id is not None  # noqa: S101

        return await self._apify_client.webhooks().create(
            actor_run_id=self._config.actor_run_id,
            event_types=event_types,
            request_url=request_url,
            payload_template=payload_template,
            ignore_ssl_errors=ignore_ssl_errors,
            do_not_retry=do_not_retry,
            idempotency_key=idempotency_key,
        )

    @classmethod
    async def set_status_message(
        cls: type[Actor],
        status_message: str,
        *,
        is_terminal: bool | None = None,
    ) -> dict | None:
        """Set the status message for the current actor run.

        Args:
            status_message (str): The status message to set to the run.
            is_terminal (bool, optional): Set this flag to True if this is the final status message of the Actor run.

        Returns:
            dict: The updated actor run object
        """
        return await cls._get_default_instance().set_status_message(status_message=status_message, is_terminal=is_terminal)

    async def _set_status_message_internal(
        self: Actor,
        status_message: str,
        *,
        is_terminal: bool | None = None,
    ) -> dict | None:
        self._raise_if_not_initialized()

        if not self.is_at_home():
            title = 'Terminal status message' if is_terminal else 'Status message'
            self.log.info(f'[{title}]: {status_message}')
            return None

        # If is_at_home() is True, config.actor_run_id is always set
        assert self._config.actor_run_id is not None  # noqa: S101

        return await self._apify_client.run(self._config.actor_run_id).update(status_message=status_message, is_status_message_terminal=is_terminal)

    @classmethod
    async def create_proxy_configuration(
        cls: type[Actor],
        *,
        actor_proxy_input: dict | None = None,  # this is the raw proxy input from the actor run input, it is not spread or snake_cased in here
        password: str | None = None,
        groups: list[str] | None = None,
        country_code: str | None = None,
        proxy_urls: list[str] | None = None,
        new_url_function: Callable[[str | None], str] | Callable[[str | None], Awaitable[str]] | None = None,
    ) -> ProxyConfiguration | None:
        """Create a ProxyConfiguration object with the passed proxy configuration.

        Configures connection to a proxy server with the provided options.
        Proxy servers are used to prevent target websites from blocking your crawlers based on IP address rate limits or blacklists.

        For more details and code examples, see the `ProxyConfiguration` class.

        Args:
            actor_proxy_input (dict, optional): Proxy configuration field from the actor input, if actor has such input field.
                If you pass this argument, all the other arguments will be inferred from it.
            password (str, optional): Password for the Apify Proxy. If not provided, will use os.environ['APIFY_PROXY_PASSWORD'], if available.
            groups (list of str, optional): Proxy groups which the Apify Proxy should use, if provided.
            country_code (str, optional): Country which the Apify Proxy should use, if provided.
            proxy_urls (list of str, optional): Custom proxy server URLs which should be rotated through.
            new_url_function (Callable, optional): Function which returns a custom proxy URL to be used.

        Returns:
            ProxyConfiguration, optional: ProxyConfiguration object with the passed configuration,
                                          or None, if no proxy should be used based on the configuration.
        """
        return await cls._get_default_instance().create_proxy_configuration(
            password=password,
            groups=groups,
            country_code=country_code,
            proxy_urls=proxy_urls,
            new_url_function=new_url_function,
            actor_proxy_input=actor_proxy_input,
        )

    async def _create_proxy_configuration_internal(
        self: Actor,
        *,
        actor_proxy_input: dict | None = None,  # this is the raw proxy input from the actor run input, it is not spread or snake_cased in here
        password: str | None = None,
        groups: list[str] | None = None,
        country_code: str | None = None,
        proxy_urls: list[str] | None = None,
        new_url_function: Callable[[str | None], str] | Callable[[str | None], Awaitable[str]] | None = None,
    ) -> ProxyConfiguration | None:
        self._raise_if_not_initialized()

        if actor_proxy_input is not None:
            if actor_proxy_input.get('useApifyProxy', False):
                country_code = country_code or actor_proxy_input.get('apifyProxyCountry')
                groups = groups or actor_proxy_input.get('apifyProxyGroups')
            else:
                proxy_urls = actor_proxy_input.get('proxyUrls', [])
                if not proxy_urls:
                    return None

        proxy_configuration = ProxyConfiguration(
            password=password,
            groups=groups,
            country_code=country_code,
            proxy_urls=proxy_urls,
            new_url_function=new_url_function,
            _actor_config=self._config,
            _apify_client=self._apify_client,
        )

        await proxy_configuration.initialize()

        return proxy_configuration
