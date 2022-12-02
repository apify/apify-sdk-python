import asyncio
import inspect
import json
from typing import Any, Callable, Optional, Set, cast

import websockets.client
from pyee.asyncio import AsyncIOEventEmitter

from .config import Configuration
from .consts import ActorEventType


class EventManager:
    """TODO: docs."""

    _platform_events_websocket: Optional[websockets.client.WebSocketClientProtocol] = None
    _process_platform_messages_task: Optional[asyncio.Task] = None
    _send_persist_state_interval_task: Optional[asyncio.Task] = None
    _send_system_info_interval_task: Optional[asyncio.Task] = None
    _listener_tasks: Set[asyncio.Task] = set()

    def __init__(self, config: Configuration) -> None:
        """TODO: docs."""
        self._config = config
        self._event_emitter = AsyncIOEventEmitter()
        self._initialized = False

    async def init(self) -> None:
        """TODO: docs."""
        if self._initialized:
            raise RuntimeError('EventManager was already initialized!')

        # Run tasks but don't await them
        if self._config.actor_events_ws_url:
            self._process_platform_messages_task = asyncio.create_task(self._process_platform_messages())
        else:
            print('ACTOR_EVENTS_WS_URL env var not set, no events from Apify platform will be emitted.')

        self._initialized = True

    async def close(self) -> None:
        """TODO: docs."""
        if not self._initialized:
            raise RuntimeError('EventManager was not initialized!')

        if self._platform_events_websocket:
            await self._platform_events_websocket.close()

        if self._process_platform_messages_task:
            await self._process_platform_messages_task

        # TODO: add optional timeout for this
        await self.wait_for_all_listeners_to_complete()

        self._initialized = False

    def on(self, event: ActorEventType, listener: Callable) -> Callable:
        """TODO: docs."""
        if not self._initialized:
            raise RuntimeError('EventManager was not initialized!')

        async def inner_wrapper(*args: Any, **kwargs: Any) -> None:
            if inspect.iscoroutinefunction(listener):
                await listener(*args, **kwargs)
            else:
                listener(*args, **kwargs)

        async def outer_wrapper(*args: Any, **kwargs: Any) -> None:
            listener_task = asyncio.create_task(inner_wrapper(*args, **kwargs))
            self._listener_tasks.add(listener_task)
            await listener_task
            self._listener_tasks.remove(listener_task)

        return self._event_emitter.add_listener(event, outer_wrapper)

    def off(self, event: ActorEventType, listener: Optional[Callable]) -> None:
        """TODO: docs."""
        if not self._initialized:
            raise RuntimeError('EventManager was not initialized!')

        if listener:
            self._event_emitter.remove_listener(event, listener)
        else:
            self._event_emitter.remove_all_listeners(event)

    def emit(self, event_name: ActorEventType, data: Any) -> None:
        """TODO: docs."""
        self._event_emitter.emit(event_name, data)

    async def wait_for_all_listeners_to_complete(self) -> None:
        """TODO: docs."""
        await asyncio.gather(*self._listener_tasks)

    async def _process_platform_messages(self) -> None:
        try:
            async with websockets.client.connect(cast(str, self._config.actor_events_ws_url)) as websocket:
                self._platform_events_websocket = websocket
                async for message in websocket:
                    try:
                        parsed_message = json.loads(message)
                        event_name = parsed_message['name']
                        event_data = parsed_message['data']

                        self._event_emitter.emit(event_name, event_data)

                    except Exception as e:
                        print('Cannot parse actor event', e)
        except Exception as e:
            print('Error in websocket connection', e)
