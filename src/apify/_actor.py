from __future__ import annotations

import asyncio
import os
import sys
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Callable, TypeVar, cast

from lazy_object_proxy import Proxy
from pydantic import AliasChoices
from typing_extensions import Self

from apify_client import ApifyClientAsync
from apify_shared.consts import ActorEnvVars, ActorExitCodes, ApifyEnvVars
from apify_shared.utils import ignore_docs, maybe_extract_enum_member_value
from crawlee import service_container
from crawlee.events._types import Event, EventPersistStateData

from apify._configuration import Configuration
from apify._consts import EVENT_LISTENERS_TIMEOUT
from apify._crypto import decrypt_input_secrets, load_private_key
from apify._models import ActorRun
from apify._platform_event_manager import EventManager, LocalEventManager, PlatformEventManager
from apify._proxy_configuration import ProxyConfiguration
from apify._utils import get_system_info, is_running_in_ipython
from apify.apify_storage_client import ApifyStorageClient
from apify.log import logger
from apify.storages import Dataset, KeyValueStore, RequestQueue

if TYPE_CHECKING:
    import logging
    from types import TracebackType

    from crawlee.proxy_configuration import _NewUrlFunction

    from apify._models import Webhook


MainReturnType = TypeVar('MainReturnType')


class _ActorType:
    """The class of `Actor`. Only make a new instance if you're absolutely sure you need to."""

    _apify_client: ApifyClientAsync
    _configuration: Configuration
    _is_exiting = False

    def __init__(self, config: Configuration | None = None) -> None:
        """Create an Actor instance.

        Note that you don't have to do this, all the functionality is accessible using the default instance
        (e.g. `Actor.open_dataset()`).

        Args:
            config: The Actor configuration to be used. If not passed, a new Configuration instance will be created.
        """
        self._configuration = config or Configuration.get_global_configuration()
        self._apify_client = self.new_client()

        self._event_manager: EventManager
        if self._configuration.is_at_home:
            self._event_manager = PlatformEventManager(
                config=self._configuration,
                persist_state_interval=self._configuration.persist_state_interval,
            )
        else:
            self._event_manager = LocalEventManager(
                system_info_interval=self._configuration.system_info_interval,
                persist_state_interval=self._configuration.persist_state_interval,
            )

        self._is_initialized = False

    @ignore_docs
    async def __aenter__(self) -> Self:
        """Initialize the Actor.

        Automatically initializes the Actor instance when you use it in an `async with ...` statement.

        When you exit the `async with` block, the `Actor.exit()` method is called, and if any exception happens while
        executing the block code, the `Actor.fail` method is called.
        """
        await self.init()
        return self

    @ignore_docs
    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        _exc_traceback: TracebackType | None,
    ) -> None:
        """Exit the Actor, handling any exceptions properly.

        When you exit the `async with` block, the `Actor.exit()` method is called, and if any exception happens while
        executing the block code, the `Actor.fail` method is called.
        """
        if not self._is_exiting:
            if exc_value:
                await self.fail(
                    exit_code=ActorExitCodes.ERROR_USER_FUNCTION_THREW.value,
                    exception=exc_value,
                )
            else:
                await self.exit()

    def __repr__(self) -> str:
        if self is cast(Proxy, Actor).__wrapped__:
            return '<apify.Actor>'

        return super().__repr__()

    def __call__(self, config: Configuration) -> Self:
        """Make a new Actor instance with a non-default configuration."""
        return self.__class__(config=config)

    @property
    def apify_client(self) -> ApifyClientAsync:
        """The ApifyClientAsync instance the Actor instance uses."""
        return self._apify_client

    @property
    def config(self) -> Configuration:
        """The Configuration instance the Actor instance uses."""
        return self._configuration

    @property
    def event_manager(self) -> EventManager:
        """The EventManager instance the Actor instance uses."""
        return self._event_manager

    @property
    def log(self) -> logging.Logger:
        """The logging.Logger instance the Actor uses."""
        return logger

    def _raise_if_not_initialized(self) -> None:
        if not self._is_initialized:
            raise RuntimeError('The Actor was not initialized!')

    async def init(self) -> None:
        """Initialize the Actor instance.

        This initializes the Actor instance. It configures the right storage client based on whether the Actor is
        running locally or on the Apify platform, it initializes the event manager for processing Actor events,
        and starts an interval for regularly sending `PERSIST_STATE` events, so that the Actor can regularly persist
        its state in response to these events.

        This method should be called immediately before performing any additional Actor actions, and it should be
        called only once.
        """
        if self._is_initialized:
            raise RuntimeError('The Actor was already initialized!')

        if self._configuration.token:
            service_container.set_cloud_storage_client(ApifyStorageClient(configuration=self._configuration))

        if self._configuration.is_at_home:
            service_container.set_default_storage_client_type('cloud')
        else:
            service_container.set_default_storage_client_type('local')

        service_container.set_event_manager(self._event_manager)

        self._is_exiting = False
        self._was_final_persist_state_emitted = False

        self.log.info('Initializing Actor...')
        self.log.info('System info', extra=get_system_info())

        # TODO: Print outdated SDK version warning (we need a new env var for this)
        # https://github.com/apify/apify-sdk-python/issues/146

        await self._event_manager.__aenter__()

        self._is_initialized = True

    async def exit(
        self,
        *,
        exit_code: int = 0,
        event_listeners_timeout: timedelta | None = EVENT_LISTENERS_TIMEOUT,
        status_message: str | None = None,
        cleanup_timeout: timedelta = timedelta(seconds=30),
    ) -> None:
        """Exit the Actor instance.

        This stops the Actor instance. It cancels all the intervals for regularly sending `PERSIST_STATE` events,
        sends a final `PERSIST_STATE` event, waits for all the event listeners to finish, and stops the event manager.

        Args:
            exit_code: The exit code with which the Actor should fail (defaults to `0`).
            event_listeners_timeout: How long should the Actor wait for Actor event listeners to finish before exiting.
            status_message: The final status message that the Actor should display.
            cleanup_timeout: How long we should wait for event listeners.
        """
        self._raise_if_not_initialized()

        self._is_exiting = True

        exit_code = maybe_extract_enum_member_value(exit_code)

        self.log.info('Exiting Actor', extra={'exit_code': exit_code})

        async def finalize() -> None:
            if status_message is not None:
                await self.set_status_message(status_message, is_terminal=True)

            # Sleep for a bit so that the listeners have a chance to trigger
            await asyncio.sleep(0.1)

            if event_listeners_timeout:
                await self._event_manager.wait_for_all_listeners_to_complete(timeout=event_listeners_timeout)

            await self._event_manager.__aexit__(None, None, None)
            cast(dict, service_container._services).clear()  # noqa: SLF001

        await asyncio.wait_for(finalize(), cleanup_timeout.total_seconds())
        self._is_initialized = False

        if is_running_in_ipython():
            self.log.debug(f'Not calling sys.exit({exit_code}) because Actor is running in IPython')
        elif os.getenv('PYTEST_CURRENT_TEST', default=False):  # noqa: PLW1508
            self.log.debug(f'Not calling sys.exit({exit_code}) because Actor is running in an unit test')
        elif hasattr(asyncio, '_nest_patched'):
            self.log.debug(f'Not calling sys.exit({exit_code}) because Actor is running in a nested event loop')
        else:
            sys.exit(exit_code)

    async def fail(
        self,
        *,
        exit_code: int = 1,
        exception: BaseException | None = None,
        status_message: str | None = None,
    ) -> None:
        """Fail the Actor instance.

        This performs all the same steps as Actor.exit(), but it additionally sets the exit code to `1` (by default).

        Args:
            exit_code: The exit code with which the Actor should fail (defaults to `1`).
            exception: The exception with which the Actor failed.
            status_message: The final status message that the Actor should display.
        """
        self._raise_if_not_initialized()

        # In IPython, we don't run `sys.exit()` during Actor exits,
        # so the exception traceback will be printed on its own
        if exception and not is_running_in_ipython():
            self.log.exception('Actor failed with an exception', exc_info=exception)

        await self.exit(exit_code=exit_code, status_message=status_message)

    def new_client(
        self,
        *,
        token: str | None = None,
        api_url: str | None = None,
        max_retries: int | None = None,
        min_delay_between_retries: timedelta | None = None,
        timeout: timedelta | None = None,
    ) -> ApifyClientAsync:
        """Return a new instance of the Apify API client.

        The `ApifyClientAsync` class is provided by the [apify-client](https://github.com/apify/apify-client-python)
        package, and it is automatically configured using the `APIFY_API_BASE_URL` and `APIFY_TOKEN` environment
        variables.

        You can override the token via the available options. That's useful if you want to use the client
        as a different Apify user than the SDK internals are using.

        Args:
            token: The Apify API token.
            api_url: The URL of the Apify API server to which to connect to. Defaults to https://api.apify.com.
            max_retries: How many times to retry a failed request at most.
            min_delay_between_retries: How long will the client wait between retrying requests
                (increases exponentially from this value).
            timeout: The socket timeout of the HTTP requests sent to the Apify API.
        """
        token = token or self._configuration.token
        api_url = api_url or self._configuration.api_base_url
        return ApifyClientAsync(
            token=token,
            api_url=api_url,
            max_retries=max_retries,
            min_delay_between_retries_millis=int(min_delay_between_retries.total_seconds() * 1000)
            if min_delay_between_retries is not None
            else None,
            timeout_secs=int(timeout.total_seconds()) if timeout else None,
        )

    async def open_dataset(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        force_cloud: bool = False,
    ) -> Dataset:
        """Open a dataset.

        Datasets are used to store structured data where each object stored has the same attributes, such as online
        store products or real estate offers. The actual data is stored either on the local filesystem or in
        the Apify cloud.

        Args:
            id: ID of the dataset to be opened. If neither `id` nor `name` are provided, the method returns
                the default dataset associated with the Actor run.
            name: Name of the dataset to be opened. If neither `id` nor `name` are provided, the method returns
                the default dataset associated with the Actor run.
            force_cloud: If set to `True` then the Apify cloud storage is always used. This way it is possible
                to combine local and cloud storage.

        Returns:
            An instance of the `Dataset` class for the given ID or name.
        """
        self._raise_if_not_initialized()

        return await Dataset.open(
            id=id,
            name=name,
            configuration=self._configuration,
            storage_client=service_container.get_storage_client(client_type='cloud' if force_cloud else None),
        )

    async def open_key_value_store(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        force_cloud: bool = False,
    ) -> KeyValueStore:
        """Open a key-value store.

        Key-value stores are used to store records or files, along with their MIME content type. The records are stored
        and retrieved using a unique key. The actual data is stored either on a local filesystem or in the Apify cloud.

        Args:
            id: ID of the key-value store to be opened. If neither `id` nor `name` are provided, the method returns
                the default key-value store associated with the Actor run.
            name: Name of the key-value store to be opened. If neither `id` nor `name` are provided, the method
                returns the default key-value store associated with the Actor run.
            force_cloud: If set to `True` then the Apify cloud storage is always used. This way it is possible
                to combine local and cloud storage.

        Returns:
            An instance of the `KeyValueStore` class for the given ID or name.
        """
        self._raise_if_not_initialized()

        return await KeyValueStore.open(
            id=id,
            name=name,
            configuration=self._configuration,
            storage_client=service_container.get_storage_client(client_type='cloud' if force_cloud else None),
        )

    async def open_request_queue(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        force_cloud: bool = False,
    ) -> RequestQueue:
        """Open a request queue.

        Request queue represents a queue of URLs to crawl, which is stored either on local filesystem or in
        the Apify cloud. The queue is used for deep crawling of websites, where you start with several URLs and then
        recursively follow links to other pages. The data structure supports both breadth-first and depth-first
        crawling orders.

        Args:
            id: ID of the request queue to be opened. If neither `id` nor `name` are provided, the method returns
                the default request queue associated with the Actor run.
            name: Name of the request queue to be opened. If neither `id` nor `name` are provided, the method returns
                the default request queue associated with the Actor run.
            force_cloud: If set to `True` then the Apify cloud storage is always used. This way it is possible
                to combine local and cloud storage.

        Returns:
            An instance of the `RequestQueue` class for the given ID or name.
        """
        self._raise_if_not_initialized()

        return await RequestQueue.open(
            id=id,
            name=name,
            configuration=self._configuration,
            storage_client=service_container.get_storage_client(client_type='cloud' if force_cloud else None),
        )

    async def push_data(self, data: dict | list[dict]) -> None:
        """Store an object or a list of objects to the default dataset of the current Actor run.

        Args:
            data: The data to push to the default dataset.
        """
        self._raise_if_not_initialized()

        if not data:
            return

        dataset = await self.open_dataset()
        await dataset.push_data(data)

    async def get_input(self) -> Any:
        """Get the Actor input value from the default key-value store associated with the current Actor run."""
        self._raise_if_not_initialized()

        input_value = await self.get_value(self._configuration.input_key)
        input_secrets_private_key = self._configuration.input_secrets_private_key_file
        input_secrets_key_passphrase = self._configuration.input_secrets_private_key_passphrase
        if input_secrets_private_key and input_secrets_key_passphrase:
            private_key = load_private_key(
                input_secrets_private_key,
                input_secrets_key_passphrase,
            )
            input_value = decrypt_input_secrets(private_key, input_value)

        return input_value

    async def get_value(self, key: str, default_value: Any = None) -> Any:
        """Get a value from the default key-value store associated with the current Actor run.

        Args:
            key: The key of the record which to retrieve.
            default_value: Default value returned in case the record does not exist.
        """
        self._raise_if_not_initialized()

        key_value_store = await self.open_key_value_store()
        return await key_value_store.get_value(key, default_value)

    async def set_value(
        self,
        key: str,
        value: Any,
        *,
        content_type: str | None = None,
    ) -> None:
        """Set or delete a value in the default key-value store associated with the current Actor run.

        Args:
            key: The key of the record which to set.
            value: The value of the record which to set, or None, if the record should be deleted.
            content_type: The content type which should be set to the value.
        """
        self._raise_if_not_initialized()

        key_value_store = await self.open_key_value_store()
        return await key_value_store.set_value(key, value, content_type=content_type)

    def on(self, event_name: Event, listener: Callable) -> Callable:
        """Add an event listener to the Actor's event manager.

        The following events can be emitted:

        - `Event.SYSTEM_INFO`: Emitted every minute; the event data contains information about the Actor's resource
          usage.

        - `Event.MIGRATING`: Emitted when the Actor on the Apify platform is about to be migrated to another worker
          server. Use this event to persist the Actor's state and gracefully stop in-progress tasks, preventing
          disruption.

        - `Event.PERSIST_STATE`: Emitted regularly (default: 60 seconds) to notify the Actor to persist its state,
          preventing work repetition after a restart. This event is emitted together with the `MIGRATING` event, where
          the `isMigrating` flag in the event data is `True`; otherwise, the flag is `False`. This event is for
          convenience; the same effect can be achieved by setting an interval and listening for the `MIGRATING` event.

        - `Event.ABORTING`: Emitted when a user aborts an Actor run on the Apify platform, allowing the Actor time
          to clean up its state if the abort is graceful.

        Args:
            event_name: The Actor event to listen for.
            listener: The function to be called when the event is emitted (can be async).
        """
        self._raise_if_not_initialized()

        self._event_manager.on(event=event_name, listener=listener)
        return listener

    def off(self, event_name: Event, listener: Callable | None = None) -> None:
        """Remove a listener, or all listeners, from an Actor event.

        Args:
            event_name: The Actor event for which to remove listeners.
            listener: The listener which is supposed to be removed. If not passed, all listeners of this event
                are removed.
        """
        self._raise_if_not_initialized()

        self._event_manager.off(event=event_name, listener=listener)

    def is_at_home(self) -> bool:
        """Return `True` when the Actor is running on the Apify platform, and `False` otherwise (e.g. local run)."""
        return self._configuration.is_at_home

    def get_env(self) -> dict:
        """Return a dictionary with information parsed from all the `APIFY_XXX` environment variables.

        For a list of all the environment variables, see the
        [Actor documentation](https://docs.apify.com/actors/development/environment-variables). If some variables
        are not defined or are invalid, the corresponding value in the resulting dictionary will be None.
        """
        self._raise_if_not_initialized()

        config = dict[str, Any]()
        for field_name, field in Configuration.model_fields.items():
            if field.deprecated:
                continue

            if field.alias:
                aliases = [field.alias]
            elif isinstance(field.validation_alias, str):
                aliases = [field.validation_alias]
            elif isinstance(field.validation_alias, AliasChoices):
                aliases = cast(list[str], field.validation_alias.choices)
            else:
                aliases = [field_name]

            for alias in aliases:
                config[alias] = getattr(self._configuration, field_name)

        env_vars = {env_var.value.lower(): env_var.name.lower() for env_var in [*ActorEnvVars, *ApifyEnvVars]}
        return {option_name: config[env_var] for env_var, option_name in env_vars.items() if env_var in config}

    async def start(
        self,
        actor_id: str,
        run_input: Any = None,
        *,
        token: str | None = None,
        content_type: str | None = None,
        build: str | None = None,
        memory_mbytes: int | None = None,
        timeout: timedelta | None = None,
        wait_for_finish: int | None = None,
        webhooks: list[Webhook] | None = None,
    ) -> ActorRun:
        """Run an Actor on the Apify platform.

        Unlike `Actor.call`, this method just starts the run without waiting for finish.

        Args:
            actor_id: The ID of the Actor to be run.
            run_input: The input to pass to the Actor run.
            token: The Apify API token to use for this request (defaults to the `APIFY_TOKEN` environment variable).
            content_type: The content type of the input.
            build: Specifies the Actor build to run. It can be either a build tag or build number. By default,
                the run uses the build specified in the default run configuration for the Actor (typically latest).
            memory_mbytes: Memory limit for the run, in megabytes. By default, the run uses a memory limit specified
                in the default run configuration for the Actor.
            timeout: Optional timeout for the run, in seconds. By default, the run uses timeout specified in
                the default run configuration for the Actor.
            wait_for_finish: The maximum number of seconds the server waits for the run to finish. By default,
                it is 0, the maximum value is 300.
            webhooks: Optional ad-hoc webhooks (https://docs.apify.com/webhooks/ad-hoc-webhooks) associated with
                the Actor run which can be used to receive a notification, e.g. when the Actor finished or failed.
                If you already have a webhook set up for the Actor or task, you do not have to add it again here.

        Returns:
            Info about the started Actor run
        """
        self._raise_if_not_initialized()

        client = self.new_client(token=token) if token else self._apify_client

        if webhooks:
            serialized_webhooks = [
                hook.model_dump(by_alias=True, exclude_unset=True, exclude_defaults=True) for hook in webhooks
            ]
        else:
            serialized_webhooks = None

        api_result = await client.actor(actor_id).start(
            run_input=run_input,
            content_type=content_type,
            build=build,
            memory_mbytes=memory_mbytes,
            timeout_secs=int(timeout.total_seconds()) if timeout is not None else None,
            wait_for_finish=wait_for_finish,
            webhooks=serialized_webhooks,
        )

        return ActorRun.model_validate(api_result)

    async def abort(
        self,
        run_id: str,
        *,
        token: str | None = None,
        status_message: str | None = None,
        gracefully: bool | None = None,
    ) -> ActorRun:
        """Abort given Actor run on the Apify platform using the current user account.

        The user account is determined by the `APIFY_TOKEN` environment variable.

        Args:
            run_id: The ID of the Actor run to be aborted.
            token: The Apify API token to use for this request (defaults to the `APIFY_TOKEN` environment variable).
            status_message: Status message of the Actor to be set on the platform.
            gracefully: If True, the Actor run will abort gracefully. It will send `aborting` and `persistState`
                events into the run and force-stop the run after 30 seconds. It is helpful in cases where you plan
                to resurrect the run later.

        Returns:
            Info about the aborted Actor run.
        """
        self._raise_if_not_initialized()

        client = self.new_client(token=token) if token else self._apify_client

        if status_message:
            await client.run(run_id).update(status_message=status_message)

        api_result = await client.run(run_id).abort(gracefully=gracefully)

        return ActorRun.model_validate(api_result)

    async def call(
        self,
        actor_id: str,
        run_input: Any = None,
        *,
        token: str | None = None,
        content_type: str | None = None,
        build: str | None = None,
        memory_mbytes: int | None = None,
        timeout: timedelta | None = None,
        webhooks: list[Webhook] | None = None,
        wait: timedelta | None = None,
    ) -> ActorRun | None:
        """Start an Actor on the Apify Platform and wait for it to finish before returning.

        It waits indefinitely, unless the wait argument is provided.

        Args:
            actor_id: The ID of the Actor to be run.
            run_input: The input to pass to the Actor run.
            token: The Apify API token to use for this request (defaults to the `APIFY_TOKEN` environment variable).
            content_type: The content type of the input.
            build: Specifies the Actor build to run. It can be either a build tag or build number. By default,
                the run uses the build specified in the default run configuration for the Actor (typically latest).
            memory_mbytes: Memory limit for the run, in megabytes. By default, the run uses a memory limit specified
                in the default run configuration for the Actor.
            timeout: Optional timeout for the run, in seconds. By default, the run uses timeout specified in
                the default run configuration for the Actor.
            webhooks: Optional webhooks (https://docs.apify.com/webhooks) associated with the Actor run, which can
                be used to receive a notification, e.g. when the Actor finished or failed. If you already have
                a webhook set up for the Actor, you do not have to add it again here.
            wait: The maximum number of seconds the server waits for the run to finish. If not provided,
                waits indefinitely.

        Returns:
            Info about the started Actor run.
        """
        self._raise_if_not_initialized()

        client = self.new_client(token=token) if token else self._apify_client

        if webhooks:
            serialized_webhooks = [
                hook.model_dump(by_alias=True, exclude_unset=True, exclude_defaults=True) for hook in webhooks
            ]
        else:
            serialized_webhooks = None

        api_result = await client.actor(actor_id).call(
            run_input=run_input,
            content_type=content_type,
            build=build,
            memory_mbytes=memory_mbytes,
            timeout_secs=int(timeout.total_seconds()) if timeout is not None else None,
            webhooks=serialized_webhooks,
            wait_secs=int(wait.total_seconds()) if wait is not None else None,
        )

        return ActorRun.model_validate(api_result)

    async def call_task(
        self,
        task_id: str,
        task_input: dict | None = None,
        *,
        build: str | None = None,
        memory_mbytes: int | None = None,
        timeout: timedelta | None = None,
        webhooks: list[Webhook] | None = None,
        wait: timedelta | None = None,
        token: str | None = None,
    ) -> ActorRun | None:
        """Start an Actor task on the Apify Platform and wait for it to finish before returning.

        It waits indefinitely, unless the wait argument is provided.

        Note that an Actor task is a saved input configuration and options for an Actor. If you want to run an Actor
        directly rather than an Actor task, please use the `Actor.call`

        Args:
            task_id: The ID of the Actor to be run.
            task_input: Overrides the input to pass to the Actor run.
            token: The Apify API token to use for this request (defaults to the `APIFY_TOKEN` environment variable).
            content_type: The content type of the input.
            build: Specifies the Actor build to run. It can be either a build tag or build number. By default,
                the run uses the build specified in the default run configuration for the Actor (typically latest).
            memory_mbytes: Memory limit for the run, in megabytes. By default, the run uses a memory limit specified
                in the default run configuration for the Actor.
            timeout: Optional timeout for the run, in seconds. By default, the run uses timeout specified in
                the default run configuration for the Actor.
            webhooks: Optional webhooks (https://docs.apify.com/webhooks) associated with the Actor run, which can
                be used to receive a notification, e.g. when the Actor finished or failed. If you already have
                a webhook set up for the Actor, you do not have to add it again here.
            wait: The maximum number of seconds the server waits for the run to finish. If not provided, waits
                indefinitely.

        Returns:
            Info about the started Actor run.
        """
        self._raise_if_not_initialized()

        client = self.new_client(token=token) if token else self._apify_client

        if webhooks:
            serialized_webhooks = [
                hook.model_dump(by_alias=True, exclude_unset=True, exclude_defaults=True) for hook in webhooks
            ]
        else:
            serialized_webhooks = None

        api_result = await client.task(task_id).call(
            task_input=task_input,
            build=build,
            memory_mbytes=memory_mbytes,
            timeout_secs=int(timeout.total_seconds()) if timeout is not None else None,
            webhooks=serialized_webhooks,
            wait_secs=int(wait.total_seconds()) if wait is not None else None,
        )

        return ActorRun.model_validate(api_result)

    async def metamorph(
        self,
        target_actor_id: str,
        run_input: Any = None,
        *,
        target_actor_build: str | None = None,
        content_type: str | None = None,
        custom_after_sleep: timedelta | None = None,
    ) -> None:
        """Transform this Actor run to an Actor run of a different Actor.

        The platform stops the current Actor container and starts a new container with the new Actor instead. All
        the default storages are preserved, and the new input is stored under the `INPUT-METAMORPH-1` key in the same
        default key-value store.

        Args:
            target_actor_id: ID of the target Actor that the run should be transformed into
            run_input: The input to pass to the new run.
            target_actor_build: The build of the target Actor. It can be either a build tag or build number.
                By default, the run uses the build specified in the default run configuration for the target Actor
                (typically the latest build).
            content_type: The content type of the input.
            custom_after_sleep: How long to sleep for after the metamorph, to wait for the container to be stopped.
        """
        self._raise_if_not_initialized()

        if not self.is_at_home():
            self.log.error('Actor.metamorph() is only supported when running on the Apify platform.')
            return

        if not custom_after_sleep:
            custom_after_sleep = self._configuration.metamorph_after_sleep

        # If is_at_home() is True, config.actor_run_id is always set
        if not self._configuration.actor_run_id:
            raise RuntimeError('actor_run_id cannot be None when running on the Apify platform.')

        await self._apify_client.run(self._configuration.actor_run_id).metamorph(
            target_actor_id=target_actor_id,
            run_input=run_input,
            target_actor_build=target_actor_build,
            content_type=content_type,
        )

        if custom_after_sleep:
            await asyncio.sleep(custom_after_sleep.total_seconds())

    async def reboot(
        self,
        *,
        event_listeners_timeout: timedelta | None = EVENT_LISTENERS_TIMEOUT,  # noqa: ARG002
        custom_after_sleep: timedelta | None = None,
    ) -> None:
        """Internally reboot this Actor.

        The system stops the current container and starts a new one, with the same run ID and default storages.

        Args:
            event_listeners_timeout: How long should the Actor wait for Actor event listeners to finish before exiting
            custom_after_sleep: How long to sleep for after the reboot, to wait for the container to be stopped.
        """
        self._raise_if_not_initialized()

        if not self.is_at_home():
            self.log.error('Actor.reboot() is only supported when running on the Apify platform.')
            return

        if not custom_after_sleep:
            custom_after_sleep = self._configuration.metamorph_after_sleep

        self._event_manager.emit(event=Event.PERSIST_STATE, event_data=EventPersistStateData(is_migrating=True))

        await self._event_manager.__aexit__(None, None, None)

        if not self._configuration.actor_run_id:
            raise RuntimeError('actor_run_id cannot be None when running on the Apify platform.')

        await self._apify_client.run(self._configuration.actor_run_id).reboot()

        if custom_after_sleep:
            await asyncio.sleep(custom_after_sleep.total_seconds())

    async def add_webhook(
        self,
        webhook: Webhook,
        *,
        ignore_ssl_errors: bool | None = None,
        do_not_retry: bool | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        """Create an ad-hoc webhook for the current Actor run.

        This webhook lets you receive a notification when the Actor run finished or failed.

        Note that webhooks are only supported for Actors running on the Apify platform. When running the Actor locally,
        the function will print a warning and have no effect.

        For more information about Apify Actor webhooks, please see the [documentation](https://docs.apify.com/webhooks).

        Args:
            webhook: The webhook to be added
            ignore_ssl_errors: Whether the webhook should ignore SSL errors returned by request_url
            do_not_retry: Whether the webhook should retry sending the payload to request_url upon failure.
            idempotency_key: A unique identifier of a webhook. You can use it to ensure that you won't create
                the same webhook multiple times.

        Returns:
            The created webhook.
        """
        self._raise_if_not_initialized()

        if not self.is_at_home():
            self.log.error('Actor.add_webhook() is only supported when running on the Apify platform.')
            return

        # If is_at_home() is True, config.actor_run_id is always set
        if not self._configuration.actor_run_id:
            raise RuntimeError('actor_run_id cannot be None when running on the Apify platform.')

        await self._apify_client.webhooks().create(
            actor_run_id=self._configuration.actor_run_id,
            event_types=webhook.event_types,
            request_url=webhook.request_url,
            payload_template=webhook.payload_template,
            ignore_ssl_errors=ignore_ssl_errors,
            do_not_retry=do_not_retry,
            idempotency_key=idempotency_key,
        )

    async def set_status_message(
        self,
        status_message: str,
        *,
        is_terminal: bool | None = None,
    ) -> ActorRun | None:
        """Set the status message for the current Actor run.

        Args:
            status_message: The status message to set to the run.
            is_terminal: Set this flag to True if this is the final status message of the Actor run.

        Returns:
            The updated Actor run object.
        """
        self._raise_if_not_initialized()

        if not self.is_at_home():
            title = 'Terminal status message' if is_terminal else 'Status message'
            self.log.info(f'[{title}]: {status_message}')
            return None

        # If is_at_home() is True, config.actor_run_id is always set
        if not self._configuration.actor_run_id:
            raise RuntimeError('actor_run_id cannot be None when running on the Apify platform.')

        api_result = await self._apify_client.run(self._configuration.actor_run_id).update(
            status_message=status_message, is_status_message_terminal=is_terminal
        )

        return ActorRun.model_validate(api_result)

    async def create_proxy_configuration(
        self,
        *,
        actor_proxy_input: dict
        | None = None,  # this is the raw proxy input from the actor run input, it is not spread or snake_cased in here
        password: str | None = None,
        groups: list[str] | None = None,
        country_code: str | None = None,
        proxy_urls: list[str] | None = None,
        new_url_function: _NewUrlFunction | None = None,
    ) -> ProxyConfiguration | None:
        """Create a ProxyConfiguration object with the passed proxy configuration.

        Configures connection to a proxy server with the provided options. Proxy servers are used to prevent target
        websites from blocking your crawlers based on IP address rate limits or blacklists.

        For more details and code examples, see the `ProxyConfiguration` class.

        Args:
            actor_proxy_input: Proxy configuration field from the Actor input, if input has such input field. If you
                pass this argument, all the other arguments will be inferred from it.
            password: Password for the Apify Proxy. If not provided, will use os.environ['APIFY_PROXY_PASSWORD'],
                if available.
            groups: Proxy groups which the Apify Proxy should use, if provided.
            country_code: Country which the Apify Proxy should use, if provided.
            proxy_urls: Custom proxy server URLs which should be rotated through.
            new_url_function: Function which returns a custom proxy URL to be used.

        Returns:
            ProxyConfiguration object with the passed configuration, or None, if no proxy should be used based
            on the configuration.
        """
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
            _actor_config=self._configuration,
            _apify_client=self._apify_client,
        )

        await proxy_configuration.initialize()

        return proxy_configuration


Actor = cast(_ActorType, Proxy(_ActorType))
"""The entry point of the SDK, through which all the Actor operations should be done."""
