import asyncio
import inspect
import json
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Set

import websockets.client
from pyee.asyncio import AsyncIOEventEmitter

from ._utils import _maybe_extract_enum_member_value, _parse_date_fields, ignore_docs
from .config import Configuration
from .consts import ActorEventTypes
from .log import logger


@ignore_docs
class EventManager:
    """A class for managing actor events.

    You shouldn't use this class directly,
    but instead use it via the `Actor.on()` and `Actor.off()` methods.
    """

    _platform_events_websocket: Optional[websockets.client.WebSocketClientProtocol] = None
    _process_platform_messages_task: Optional[asyncio.Task] = None
    _send_persist_state_interval_task: Optional[asyncio.Task] = None
    _send_system_info_interval_task: Optional[asyncio.Task] = None
    _listener_tasks: Set[asyncio.Task]
    _listeners_to_wrappers: Dict[ActorEventTypes, Dict[Callable, List[Callable]]]
    _connected_to_platform_websocket: Optional[asyncio.Future] = None

    def __init__(self, config: Configuration) -> None:
        """Crate an instance of EventManager.

        Args:
            config (Configuration): The actor configuration to be used in this event manager.
        """
        self._config = config
        self._event_emitter = AsyncIOEventEmitter()
        self._initialized = False
        self._listener_tasks = set()
        self._listeners_to_wrappers = defaultdict(lambda: defaultdict(list))

    async def init(self) -> None:
        """Initialize the event manager.

        When running this on the Apify Platform, this will start processing events
        send by the platform to the events websocket and emitting them as events
        that can be listened to by the `Actor.on()` method.
        """
        if self._initialized:
            raise RuntimeError('EventManager was already initialized!')

        # Run tasks but don't await them
        if self._config.actor_events_ws_url:
            self._connected_to_platform_websocket = asyncio.Future()
            self._process_platform_messages_task = asyncio.create_task(self._process_platform_messages())
            is_connected = await self._connected_to_platform_websocket
            if not is_connected:
                raise RuntimeError('Error connecting to platform events websocket!')
        else:
            logger.debug('APIFY_ACTOR_EVENTS_WS_URL env var not set, no events from Apify platform will be emitted.')

        self._initialized = True

    async def close(self, event_listeners_timeout_secs: Optional[float] = None) -> None:
        """Initialize the event manager.

        This will stop listening for the platform events,
        and it will wait for all the event listeners to finish.

        Args:
            event_listeners_timeout_secs (float, optional): Optional timeout after which the pending event listeners are canceled.
        """
        if not self._initialized:
            raise RuntimeError('EventManager was not initialized!')

        if self._platform_events_websocket:
            await self._platform_events_websocket.close()

        if self._process_platform_messages_task:
            await self._process_platform_messages_task

        await self.wait_for_all_listeners_to_complete(timeout_secs=event_listeners_timeout_secs)

        self._event_emitter.remove_all_listeners()

        self._initialized = False

    def on(self, event_name: ActorEventTypes, listener: Callable) -> Callable:
        """Add an event listener to the event manager.

        Args:
            event_name (ActorEventTypes): The actor event for which to listen to.
            listener (Callable): The function which is to be called when the event is emitted (can be async).
        """
        if not self._initialized:
            raise RuntimeError('EventManager was not initialized!')

        event_name = _maybe_extract_enum_member_value(event_name)

        async def inner_wrapper(*args: Any, **kwargs: Any) -> None:
            if inspect.iscoroutinefunction(listener):
                await listener(*args, **kwargs)
            else:
                listener(*args, **kwargs)

        async def outer_wrapper(*args: Any, **kwargs: Any) -> None:
            listener_task = asyncio.create_task(inner_wrapper(*args, **kwargs))
            self._listener_tasks.add(listener_task)
            try:
                await listener_task
            except asyncio.CancelledError:
                raise
            except Exception:
                # We need to swallow the exception and just log it here, since it could break the event emitter otherwise
                logger.exception('Exception in event listener', extra={'event_name': event_name, 'listener_name': listener.__name__})
            finally:
                self._listener_tasks.remove(listener_task)

        self._listeners_to_wrappers[event_name][listener].append(outer_wrapper)

        return self._event_emitter.add_listener(event_name, outer_wrapper)

    def off(self, event_name: ActorEventTypes, listener: Optional[Callable] = None) -> None:
        """Remove a listener, or all listeners, from an actor event.

        Args:
            event_name (ActorEventTypes): The actor event for which to remove listeners.
            listener (Callable, optional): The listener which is supposed to be removed. If not passed, all listeners of this event are removed.
        """
        if not self._initialized:
            raise RuntimeError('EventManager was not initialized!')

        event_name = _maybe_extract_enum_member_value(event_name)

        if listener:
            for listener_wrapper in self._listeners_to_wrappers[event_name][listener]:
                self._event_emitter.remove_listener(event_name, listener_wrapper)
            self._listeners_to_wrappers[event_name][listener] = []
        else:
            self._listeners_to_wrappers[event_name] = defaultdict(list)
            self._event_emitter.remove_all_listeners(event_name)

    def emit(self, event_name: ActorEventTypes, data: Any) -> None:
        """Emit an actor event manually.

        Args:
            event_name (ActorEventTypes): The actor event which should be emitted.
            data (Any): The data that should be emitted with the event.
        """
        event_name = _maybe_extract_enum_member_value(event_name)

        self._event_emitter.emit(event_name, data)

    async def wait_for_all_listeners_to_complete(self, *, timeout_secs: Optional[float] = None) -> None:
        """Wait for all event listeners which are currently being executed to complete.

        Args:
            timeout_secs (float, optional): Timeout for the wait. If the event listeners don't finish until the timeout, they will be canceled.
        """
        async def _wait_for_listeners() -> None:
            results = await asyncio.gather(*self._listener_tasks, return_exceptions=True)
            for result in results:
                if result is Exception:
                    logger.exception('Event manager encountered an exception in one of the event listeners', exc_info=result)

        if timeout_secs:
            _, pending = await asyncio.wait([asyncio.create_task(_wait_for_listeners())], timeout=timeout_secs)
            if pending:
                logger.warning('Timed out waiting for event listeners to complete, unfinished event listeners will be canceled')
                for pending_task in pending:
                    pending_task.cancel()
                    try:
                        await pending_task
                    except asyncio.CancelledError:
                        pass
        else:
            await _wait_for_listeners()

    async def _process_platform_messages(self) -> None:
        # This should be called only on the platform, where we have the ACTOR_EVENTS_WS_URL configured
        assert self._config.actor_events_ws_url is not None
        assert self._connected_to_platform_websocket is not None

        try:
            async with websockets.client.connect(self._config.actor_events_ws_url) as websocket:
                self._platform_events_websocket = websocket
                self._connected_to_platform_websocket.set_result(True)
                async for message in websocket:
                    try:
                        parsed_message = json.loads(message)
                        assert isinstance(parsed_message, dict)
                        parsed_message = _parse_date_fields(parsed_message)
                        event_name = parsed_message['name']
                        event_data = parsed_message.get('data')  # 'data' can be missing

                        self._event_emitter.emit(event_name, event_data)

                    except Exception:
                        logger.exception('Cannot parse actor event', extra={'message': message})
        except Exception:
            logger.exception('Error in websocket connection')
            self._connected_to_platform_websocket.set_result(False)
