import asyncio
import datetime
import functools
import inspect
from types import TracebackType
from typing import Any, Callable, Coroutine, Dict, List, Optional, Type, TypeVar, cast

from apify_client import ApifyClientAsync
from apify_client.clients import DatasetClientAsync, KeyValueStoreClientAsync, RequestQueueClientAsync
from apify_client.consts import WebhookEventType

from ._utils import (
    _fetch_and_parse_env_var,
    _get_cpu_usage_percent,
    _get_memory_usage_bytes,
    _log_system_info,
    _run_func_at_interval_async,
    classproperty,
)
from .config import Configuration
from .consts import ActorEventType, ApifyEnvVars
from .event_manager import EventManager

MainReturnType = TypeVar('MainReturnType')


# This metaclass is needed so you can do `with Actor: ...` instead of `with Actor() as a: ...`
# and have automatic `Actor.init()` and `Actor.exit()`
# TODO: decide if this mumbo jumbo is worth it or not, or if it maybe breaks something
class _ActorContextManager(type):
    @staticmethod
    async def __aenter__() -> Type['Actor']:
        await Actor.init()
        return Actor

    @staticmethod
    async def __aexit__(
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> bool:
        if exc_type:
            print(exc_type)
            print(exc_value)
            print(traceback)
            await Actor.fail()
            return True
        else:
            await Actor.exit()
            return False


class Actor(metaclass=_ActorContextManager):
    """Class representing an Apify Actor."""

    _config: Optional[Configuration] = None
    _default_instance: Optional['Actor'] = None

    def __init__(self, config: Optional[Configuration] = None) -> None:
        """TODO: docs."""
        # To have methods which work the same as classmethods and instance methods,
        # so you can do both Actor.xxx() and Actor().xxx(),
        # we need to have an `_xxx_internal` instance method which contains the actual implementation of the method,
        # and then in the instance constructor overwrite the `xxx` classmethod with the `_xxx_internal` instance method,
        # while copying the annotations, types and so on.
        self.init = functools.update_wrapper(self._init_internal, self.init)  # type: ignore
        self.exit = functools.update_wrapper(self._exit_internal, self.exit)  # type: ignore
        self.fail = functools.update_wrapper(self._fail_internal, self.fail)  # type: ignore
        self.main = functools.update_wrapper(self._main_internal, self.main)  # type: ignore
        self.new_client = functools.update_wrapper(self._new_client_internal, self.new_client)  # type: ignore

        self.open_dataset = functools.update_wrapper(self._open_dataset_internal, self.open_dataset)  # type: ignore
        self.open_key_value_store = functools.update_wrapper(self._open_key_value_store_internal, self.open_key_value_store)  # type: ignore
        self.open_request_queue = functools.update_wrapper(self._open_request_queue_internal, self.open_request_queue)  # type: ignore
        self.push_data = functools.update_wrapper(self._push_data_internal, self.push_data)  # type: ignore
        self.get_input = functools.update_wrapper(self._get_input_internal, self.get_input)  # type: ignore
        self.get_value = functools.update_wrapper(self._get_value_internal, self.get_value)  # type: ignore
        self.set_value = functools.update_wrapper(self._set_value_internal, self.set_value)  # type: ignore

        self.on = functools.update_wrapper(self._on_internal, self.on)  # type: ignore
        self.off = functools.update_wrapper(self._off_internal, self.off)  # type: ignore

        self.is_at_home = functools.update_wrapper(self._is_at_home_internal, self.is_at_home)  # type: ignore
        self.get_env = functools.update_wrapper(self._get_env_internal, self.get_env)  # type: ignore

        self.start = functools.update_wrapper(self._start_internal, self.start)  # type: ignore
        self.call = functools.update_wrapper(self._call_internal, self.call)  # type: ignore
        self.call_task = functools.update_wrapper(self._call_task_internal, self.call_task)  # type: ignore
        self.abort = functools.update_wrapper(self._abort_internal, self.abort)  # type: ignore
        self.metamorph = functools.update_wrapper(self._metamorph_internal, self.metamorph)  # type: ignore
        self.reboot = functools.update_wrapper(self._reboot_internal, self.reboot)  # type: ignore
        self.add_webhook = functools.update_wrapper(self._add_webhook_internal, self.add_webhook)  # type: ignore
        self.set_status_message = functools.update_wrapper(self._set_status_message_internal, self.set_status_message)  # type: ignore

        self.config = config or Configuration()
        self.apify_client = self.new_client()
        self.event_manager = EventManager(config=self.config)

        self._is_initialized = False

    async def __aenter__(self) -> 'Actor':
        """TODO: docs."""
        await self.init()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> bool:
        """TODO: docs."""
        # TODO: fail with the right exception
        if exc_type:
            print(exc_type)
            print(exc_value)
            print(traceback)
            await self.fail()
            return True
        else:
            await self.exit()
            return False

    @classproperty
    def apify_client(cls) -> ApifyClientAsync:  # noqa: N805
        """TODO: docs."""
        return cls._get_default_instance().apify_client

    @classproperty
    def config(cls) -> Configuration:  # noqa: N805
        """TODO: docs."""
        if not cls._config:
            cls._config = Configuration()
        return cls._config

    def _raise_if_not_initialized(self) -> None:
        if not self._is_initialized:
            raise RuntimeError('The actor was not initialized!')

    @classmethod
    def _get_default_instance(cls) -> 'Actor':
        if not cls._default_instance:
            cls._default_instance = Actor(config=cls.config)

        return cls._default_instance

    @classmethod
    async def init(cls) -> None:
        """TODO: docs."""
        return await cls._get_default_instance().init()

    async def _init_internal(self) -> None:
        if self._is_initialized:
            raise RuntimeError('The actor was already initialized!')

        print('Initializing actor...')
        _log_system_info()

        await self.event_manager.init()

        self._send_persist_state_interval_task = asyncio.create_task(
            _run_func_at_interval_async(
                lambda: self.event_manager.emit(ActorEventType.PERSIST_STATE, {'isMigrating': False}),
                self.config.persist_state_interval_millis / 1000,
            ),
        )

        if not self.is_at_home():
            self._send_system_info_interval_task = asyncio.create_task(
                _run_func_at_interval_async(
                    lambda: self.event_manager.emit(ActorEventType.SYSTEM_INFO, self._get_system_info()),
                    self.config.system_info_interval_millis / 1000,
                ),
            )

        self.event_manager.on(ActorEventType.MIGRATING, self._respond_to_migrating_event)

        # The CPU usage is calculated as an average between two last calls to psutil
        # We need to make a first, dummy call, so the next calls have something to compare itself agains
        _get_cpu_usage_percent()

        self._is_initialized = True

    def _get_system_info(self) -> Dict:
        cpu_usage_percent = _get_cpu_usage_percent()
        memory_usage_bytes = _get_memory_usage_bytes()
        # This is in camel case to be compatible with the events from the platform
        result = {
            'createdAt': datetime.datetime.now().isoformat(timespec='milliseconds') + 'Z',
            'cpuCurrentUsage': cpu_usage_percent,
            'memCurrentBytes': memory_usage_bytes,
        }
        if self.config.max_used_cpu_ratio:
            result['isCpuOverloaded'] = (cpu_usage_percent > 100 * self.config.max_used_cpu_ratio)

        return result

    def _respond_to_migrating_event(self) -> None:
        # Don't emit any more regular persist state events
        if self._send_persist_state_interval_task:
            self._send_persist_state_interval_task.cancel()
        self.event_manager.emit(ActorEventType.PERSIST_STATE, {'is_migrating': True})

    @classmethod
    async def exit(cls, *, exit_code: int = 0) -> None:
        """TODO: docs."""
        return await cls._get_default_instance().exit(exit_code=exit_code)

    async def _exit_internal(self, *, exit_code: int = 0) -> None:
        self._raise_if_not_initialized()

        print(f'Exiting actor with exit code {exit_code}')

        if self._send_persist_state_interval_task and not self._send_persist_state_interval_task.cancelled():
            self._send_persist_state_interval_task.cancel()
            await self._send_persist_state_interval_task

        if self._send_system_info_interval_task and not self._send_system_info_interval_task.cancelled():
            self._send_system_info_interval_task.cancel()
            await self._send_system_info_interval_task

        # Send final persist state event
        self.event_manager.emit(ActorEventType.PERSIST_STATE, {'isMigrating': False})

        # Sleep for a bit so that the listeners have a chance to trigger,
        await asyncio.sleep(0.1)

        # TODO: optional timeout for waiting for all event handlers to finish
        await self.event_manager.close()

        # TODO: once we have in-memory storage, teardown the in-memory storage client here

        self._is_initialized = False

        # TODO: something like process.exit here, but asyncio-friendly

    @classmethod
    async def fail(cls, *, exit_code: int = 1) -> None:
        """TODO: docs."""
        return await cls._get_default_instance().fail(exit_code=exit_code)

    async def _fail_internal(self, *, exit_code: int = 1) -> None:
        self._raise_if_not_initialized()

        await self.exit(exit_code=exit_code)

    @classmethod
    async def main(cls, main_actor_coro: Coroutine[Any, Any, MainReturnType]) -> Optional[MainReturnType]:
        """TODO: docs."""
        return await cls._get_default_instance().main(
            main_actor_coro=main_actor_coro,
        )

    async def _main_internal(self, main_actor_coro: Coroutine[Any, Any, MainReturnType]) -> Optional[MainReturnType]:
        if not inspect.iscoroutine(main_actor_coro):
            raise TypeError(f'First argument passed to Actor.main() must be a coroutine, but instead it was {type(main_actor_coro)}')

        await self.init()
        try:
            res = await main_actor_coro
            await self.exit()
            return cast(MainReturnType, res)
        except Exception as e:
            print(e)
            await self.exit(exit_code=1)
        return None

    @classmethod
    def new_client(
        cls,
        *,
        token: Optional[str] = None,
        api_url: Optional[str] = None,
        max_retries: Optional[int] = None,
        min_delay_between_retries_millis: Optional[int] = None,
        timeout_secs: Optional[int] = None,
    ) -> ApifyClientAsync:
        """TODO: docs."""
        return cls._get_default_instance().new_client(
            token=token,
            api_url=api_url,
            max_retries=max_retries,
            min_delay_between_retries_millis=min_delay_between_retries_millis,
            timeout_secs=timeout_secs,
        )

    def _new_client_internal(
        self,
        *,
        token: Optional[str] = None,
        api_url: Optional[str] = None,
        max_retries: Optional[int] = None,
        min_delay_between_retries_millis: Optional[int] = None,
        timeout_secs: Optional[int] = None,
    ) -> ApifyClientAsync:
        token = token or self.config.token
        api_url = api_url or self.config.api_base_url
        return ApifyClientAsync(
            token=token,
            api_url=api_url,
            max_retries=max_retries,
            min_delay_between_retries_millis=min_delay_between_retries_millis,
            timeout_secs=timeout_secs,
        )

    # TODO: create proper Dataset, KeyValueStore and RequestQueue class
    @classmethod
    async def open_dataset(cls, dataset_id_or_name: Optional[str] = None) -> DatasetClientAsync:
        """TODO: docs."""
        return await cls._get_default_instance().open_dataset(dataset_id_or_name=dataset_id_or_name)

    async def _open_dataset_internal(self, dataset_id_or_name: Optional[str] = None) -> DatasetClientAsync:
        # TODO: this should return a Dataset class rather than the raw client

        self._raise_if_not_initialized()

        if not dataset_id_or_name:
            dataset_id_or_name = self.config.default_dataset_id

        dataset = await self.apify_client.datasets().get_or_create(name=dataset_id_or_name)
        return self.apify_client.dataset(dataset['id'])

    @classmethod
    async def open_key_value_store(cls, key_value_store_id_or_name: Optional[str] = None) -> KeyValueStoreClientAsync:
        """TODO: docs."""
        return await cls._get_default_instance().open_key_value_store(key_value_store_id_or_name=key_value_store_id_or_name)

    async def _open_key_value_store_internal(self, key_value_store_id_or_name: Optional[str] = None) -> KeyValueStoreClientAsync:
        # TODO: this should return a KeyValueStore class rather than the raw client

        self._raise_if_not_initialized()

        if not key_value_store_id_or_name:
            key_value_store_id_or_name = self.config.default_key_value_store_id

        key_value_store = await self.apify_client.key_value_stores().get_or_create(name=key_value_store_id_or_name)
        return self.apify_client.key_value_store(key_value_store['id'])

    @classmethod
    async def open_request_queue(cls, request_queue_id_or_name: Optional[str] = None) -> RequestQueueClientAsync:
        """TODO: docs."""
        return await cls._get_default_instance().open_request_queue(request_queue_id_or_name=request_queue_id_or_name)

    async def _open_request_queue_internal(self, request_queue_id_or_name: Optional[str] = None) -> RequestQueueClientAsync:
        # TODO: this should return a RequestQueue class rather than the raw client

        self._raise_if_not_initialized()

        if not request_queue_id_or_name:
            request_queue_id_or_name = self.config.default_request_queue_id

        request_queue = await self.apify_client.request_queues().get_or_create(name=request_queue_id_or_name)
        return self.apify_client.request_queue(request_queue['id'])

    @classmethod
    async def push_data(cls, data: Any) -> None:
        """TODO: docs."""
        return await cls._get_default_instance().push_data(data=data)

    async def _push_data_internal(self, data: Any) -> None:
        self._raise_if_not_initialized()

        if not data:
            return

        if not isinstance(data, list):
            data = [data]

        dataset_client = await self.open_dataset()
        return await dataset_client.push_items(data)

    @classmethod
    async def get_input(cls) -> Any:
        """TODO: docs."""
        return await cls._get_default_instance().get_input()

    async def _get_input_internal(self) -> Any:
        self._raise_if_not_initialized()

        # TODO: decryption

        return await self.get_value(self.config.input_key)

    @classmethod
    async def get_value(cls, key: str) -> Any:
        """TODO: docs."""
        return await cls._get_default_instance().get_value(key=key)

    async def _get_value_internal(self, key: str) -> Any:
        self._raise_if_not_initialized()

        key_value_store_client = await self.open_key_value_store()
        record = await key_value_store_client.get_record(key)
        if record:
            return record['value']
        return None

    @classmethod
    async def set_value(cls, key: str, value: Any, options: Optional[Dict] = None) -> None:
        """TODO: docs."""
        return await cls._get_default_instance().set_value(
            key=key,
            value=value,
            options=options,
        )

    async def _set_value_internal(self, key: str, value: Any, options: Optional[Dict] = None) -> None:
        self._raise_if_not_initialized()

        content_type = options['content_type'] if options else None

        key_value_store_client = await self.open_key_value_store()
        return await key_value_store_client.set_record(key, value, content_type=content_type)

    @classmethod
    def on(cls, event: ActorEventType, listener: Callable) -> Callable:
        """TODO: docs."""
        return cls._get_default_instance().on(event, listener)

    def _on_internal(self, event: ActorEventType, listener: Callable) -> Callable:
        self._raise_if_not_initialized()

        return self.event_manager.on(event, listener)

    @classmethod
    def off(cls, event: ActorEventType, listener: Optional[Callable]) -> None:
        """TODO: docs."""
        return cls._get_default_instance().off(event, listener)

    def _off_internal(self, event: ActorEventType, listener: Optional[Callable]) -> None:
        self._raise_if_not_initialized()

        return self.event_manager.off(event, listener)

    @classmethod
    def is_at_home(cls) -> bool:
        """TODO: docs."""
        return cls._get_default_instance().is_at_home()

    def _is_at_home_internal(self) -> bool:
        return self.config.is_at_home

    @classmethod
    def get_env(cls) -> Dict:
        """TODO: docs."""
        return cls._get_default_instance().get_env()

    def _get_env_internal(self) -> Dict:
        self._raise_if_not_initialized()

        return {
            env_var.name.lower(): _fetch_and_parse_env_var(env_var.value) for env_var in ApifyEnvVars
        }

    @classmethod
    async def start(
        cls,
        actor_id: str,
        run_input: Optional[Any] = None,
        *,
        token: Optional[str] = None,
        content_type: Optional[str] = None,
        build: Optional[str] = None,
        memory_mbytes: Optional[int] = None,
        timeout_secs: Optional[int] = None,
        wait_for_finish: Optional[int] = None,
        webhooks: Optional[List[Dict]] = None,
    ) -> Dict:
        """TODO: docs."""
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
        self,
        actor_id: str,
        run_input: Optional[Any] = None,
        *,
        token: Optional[str] = None,
        content_type: Optional[str] = None,
        build: Optional[str] = None,
        memory_mbytes: Optional[int] = None,
        timeout_secs: Optional[int] = None,
        wait_for_finish: Optional[int] = None,
        webhooks: Optional[List[Dict]] = None,
    ) -> Dict:
        self._raise_if_not_initialized()

        if token:
            client = self.new_client(token=token)
        else:
            client = self.apify_client

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
        cls,
        run_id: str,
        *,
        token: Optional[str] = None,
        gracefully: Optional[bool] = None,
    ) -> Dict:
        """TODO: docs."""
        return await cls._get_default_instance().abort(
            run_id=run_id,
            token=token,
            gracefully=gracefully,
        )

    async def _abort_internal(
        self,
        run_id: str,
        *,
        gracefully: Optional[bool] = None,
        status_message: Optional[str] = None,
        token: Optional[str] = None,
    ) -> Dict:
        self._raise_if_not_initialized()

        if token:
            client = self.new_client(token=token)
        else:
            client = self.apify_client

        if status_message:
            await client.run(run_id).update(status_message=status_message)

        return await client.run(run_id).abort(gracefully=gracefully)

    @classmethod
    async def call(
        cls,
        actor_id: str,
        run_input: Optional[Any] = None,
        *,
        token: Optional[str] = None,
        content_type: Optional[str] = None,
        build: Optional[str] = None,
        memory_mbytes: Optional[int] = None,
        timeout_secs: Optional[int] = None,
        webhooks: Optional[List[Dict]] = None,
        wait_secs: Optional[int] = None,
    ) -> Optional[Dict]:
        """TODO: docs."""
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
        self,
        actor_id: str,
        run_input: Optional[Any] = None,
        *,
        token: Optional[str] = None,
        content_type: Optional[str] = None,
        build: Optional[str] = None,
        memory_mbytes: Optional[int] = None,
        timeout_secs: Optional[int] = None,
        webhooks: Optional[List[Dict]] = None,
        wait_secs: Optional[int] = None,
    ) -> Optional[Dict]:
        self._raise_if_not_initialized()

        if token:
            client = self.new_client(token=token)
        else:
            client = self.apify_client

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
        cls,
        task_id: str,
        task_input: Optional[Dict[str, Any]] = None,
        *,
        build: Optional[str] = None,
        memory_mbytes: Optional[int] = None,
        timeout_secs: Optional[int] = None,
        webhooks: Optional[List[Dict]] = None,
        wait_secs: Optional[int] = None,
        token: Optional[str] = None,
    ) -> Optional[Dict]:
        """TODO: docs."""
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
        self,
        task_id: str,
        task_input: Optional[Dict[str, Any]] = None,
        *,
        build: Optional[str] = None,
        memory_mbytes: Optional[int] = None,
        timeout_secs: Optional[int] = None,
        webhooks: Optional[List[Dict]] = None,
        wait_secs: Optional[int] = None,
        token: Optional[str] = None,
    ) -> Optional[Dict]:
        self._raise_if_not_initialized()

        if token:
            client = self.new_client(token=token)
        else:
            client = self.apify_client

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
        cls,
        target_actor_id: str,
        run_input: Optional[Any] = None,
        *,
        target_actor_build: Optional[str] = None,
        content_type: Optional[str] = None,
        custom_after_sleep_millis: Optional[int] = None,
    ) -> None:
        """TODO: docs."""
        return await cls._get_default_instance().metamorph(
            target_actor_id=target_actor_id,
            target_actor_build=target_actor_build,
            run_input=run_input,
            content_type=content_type,
            custom_after_sleep_millis=custom_after_sleep_millis,
        )

    async def _metamorph_internal(
        self,
        target_actor_id: str,
        run_input: Optional[Any] = None,
        *,
        target_actor_build: Optional[str] = None,
        content_type: Optional[str] = None,
        custom_after_sleep_millis: Optional[int] = None,
    ) -> None:
        self._raise_if_not_initialized()

        if not self.is_at_home():
            print('Actor.metamorph() is only supported when running on the Apify platform.')
            return

        if not custom_after_sleep_millis:
            custom_after_sleep_millis = self.config.metamorph_after_sleep_millis

        # If is_at_home() is True, config.actor_run_id is always set
        actor_run_id = cast(str, self.config.actor_run_id)

        await self.apify_client.run(actor_run_id).metamorph(
            target_actor_id=target_actor_id,
            run_input=run_input,
            target_actor_build=target_actor_build,
            content_type=content_type,
        )

        if custom_after_sleep_millis:
            await asyncio.sleep(custom_after_sleep_millis / 1000)

    @classmethod
    async def reboot(cls) -> None:
        """TODO: docs."""
        return await cls._get_default_instance().reboot()

    async def _reboot_internal(self) -> None:
        self._raise_if_not_initialized()

        if not self.is_at_home():
            print('Actor.reboot() is only supported when running on the Apify platform.')
            return

        self.event_manager.emit(ActorEventType.PERSIST_STATE, {'isMigrating': True})

        await self.event_manager.wait_for_all_listeners_to_complete()

        # If is_at_home() is True, config.actor_id is always set
        actor_id = cast(str, self.config.actor_id)

        await self.metamorph(actor_id)

    @classmethod
    async def add_webhook(
        cls,
        *,
        event_types: List[WebhookEventType],
        request_url: str,
        payload_template: Optional[str] = None,
        ignore_ssl_errors: Optional[bool] = None,
        do_not_retry: Optional[bool] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict:
        """TODO: docs."""
        return await cls._get_default_instance().add_webhook(
            event_types=event_types,
            request_url=request_url,
            payload_template=payload_template,
            ignore_ssl_errors=ignore_ssl_errors,
            do_not_retry=do_not_retry,
            idempotency_key=idempotency_key,
        )

    async def _add_webhook_internal(
        self,
        *,
        event_types: List[WebhookEventType],
        request_url: str,
        payload_template: Optional[str] = None,
        ignore_ssl_errors: Optional[bool] = None,
        do_not_retry: Optional[bool] = None,
        idempotency_key: Optional[str] = None,
    ) -> Optional[Dict]:
        self._raise_if_not_initialized()

        if not self.is_at_home():
            print('Actor.add_webhook() is only supported when running on the Apify platform.')
            return None

        # If is_at_home() is True, config.actor_run_id is always set
        actor_run_id = self.config.actor_run_id

        return await self.apify_client.webhooks().create(
            actor_run_id=actor_run_id,
            event_types=event_types,
            request_url=request_url,
            payload_template=payload_template,
            ignore_ssl_errors=ignore_ssl_errors,
            do_not_retry=do_not_retry,
            idempotency_key=idempotency_key,
        )

    @classmethod
    async def set_status_message(cls, status_message: str) -> Dict:
        """TODO: docs."""
        return await cls._get_default_instance().set_status_message(status_message=status_message)

    async def _set_status_message_internal(self, status_message: str) -> Dict:
        self._raise_if_not_initialized()

        # If is_at_home() is True, config.actor_run_id is always set
        actor_run_id = cast(str, self.config.actor_run_id)

        return await self.apify_client.run(actor_run_id).update(status_message=status_message)
