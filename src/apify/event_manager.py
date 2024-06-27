from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Annotated, Any, Literal, Union

import websockets.client
from apify_shared.utils import ignore_docs
from crawlee.events.event_manager import EventManager, EventManagerOptions
from crawlee.events.local_event_manager import LocalEventManager
from crawlee.events.types import Event, EventAbortingData, EventExitData, EventMigratingData, EventPersistStateData, EventSystemInfoData
from pydantic import BaseModel, Discriminator, Field, TypeAdapter
from typing_extensions import Self, Unpack, override

from apify.log import logger

if TYPE_CHECKING:
    from types import TracebackType

    from apify.config import Configuration


__all__ = ['EventManager', 'LocalEventManager', 'PlatformEventManager']


class PersistStateEvent(BaseModel):
    name: Literal[Event.PERSIST_STATE]
    data: Annotated[EventPersistStateData, Field(default_factory=lambda: EventPersistStateData(is_migrating=False))]


class SystemInfoEvent(BaseModel):
    name: Literal[Event.SYSTEM_INFO]
    data: EventSystemInfoData


class MigratingEvent(BaseModel):
    name: Literal[Event.MIGRATING]
    data: Annotated[EventMigratingData, Field(default_factory=EventMigratingData)]


class AbortingEvent(BaseModel):
    name: Literal[Event.ABORTING]
    data: Annotated[EventAbortingData, Field(default_factory=EventAbortingData)]


class ExitEvent(BaseModel):
    name: Literal[Event.EXIT]
    data: Annotated[EventExitData, Field(default_factory=EventExitData)]


class EventWithoutData(BaseModel):
    name: Literal[
        Event.SESSION_RETIRED,
        Event.BROWSER_LAUNCHED,
        Event.BROWSER_RETIRED,
        Event.BROWSER_CLOSED,
        Event.PAGE_CREATED,
        Event.PAGE_CLOSED,
    ]
    data: Any = None


class UnknownEvent(BaseModel):
    name: str
    data: Annotated[dict[str, Any], Field(default_factory=dict)]


EventMessage = Union[
    PersistStateEvent,
    SystemInfoEvent,
    MigratingEvent,
    AbortingEvent,
    ExitEvent,
    EventWithoutData,
]


event_data_adapter: TypeAdapter[EventMessage | UnknownEvent] = TypeAdapter(
    Union[
        Annotated[
            EventMessage,
            Discriminator('name'),
        ],
        UnknownEvent,
    ]
)


@ignore_docs
class PlatformEventManager(EventManager):
    """A class for managing actor events.

    You shouldn't use this class directly,
    but instead use it via the `Actor.on()` and `Actor.off()` methods.
    """

    _platform_events_websocket: websockets.client.WebSocketClientProtocol | None = None
    _process_platform_messages_task: asyncio.Task | None = None
    _send_system_info_interval_task: asyncio.Task | None = None
    _connected_to_platform_websocket: asyncio.Future = asyncio.Future()

    def __init__(self, config: Configuration, **kwargs: Unpack[EventManagerOptions]) -> None:
        """Create an instance of the EventManager.

        Args:
            config (Configuration): The actor configuration to be used in this event manager.
            kwargs (EventManagerOptions): Event manager options - forwarded to the base class
        """
        super().__init__(**kwargs)

        self._config = config
        self._listener_tasks = set()
        self._connected_to_platform_websocket = asyncio.Future[bool]()

    @override
    async def __aenter__(self) -> Self:
        await super().__aenter__()
        self._connected_to_platform_websocket = asyncio.Future()

        # Run tasks but don't await them
        if self._config.actor_events_ws_url:
            self._process_platform_messages_task = asyncio.create_task(self._process_platform_messages(self._config.actor_events_ws_url))
            is_connected = await self._connected_to_platform_websocket
            if not is_connected:
                raise RuntimeError('Error connecting to platform events websocket!')
        else:
            logger.debug('APIFY_ACTOR_EVENTS_WS_URL env var not set, no events from Apify platform will be emitted.')

        return self

    @override
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        if self._platform_events_websocket:
            await self._platform_events_websocket.close()

        if self._process_platform_messages_task:
            await self._process_platform_messages_task

        await super().__aexit__(exc_type, exc_value, exc_traceback)

    async def _process_platform_messages(self, ws_url: str) -> None:
        try:
            async with websockets.client.connect(ws_url) as websocket:
                self._platform_events_websocket = websocket
                self._connected_to_platform_websocket.set_result(True)

                async for message in websocket:
                    try:
                        parsed_message = event_data_adapter.validate_json(message)

                        if isinstance(parsed_message, UnknownEvent):
                            logger.info(f'Unknown message received: event_name={parsed_message.name}, event_data={parsed_message.data}')
                            continue

                        self.emit(event=parsed_message.name, event_data=parsed_message.data)

                        if parsed_message.name == Event.MIGRATING:
                            await self._emit_persist_state_event_rec_task.stop()
                            self.emit(event=Event.PERSIST_STATE, event_data=EventPersistStateData(is_migrating=True))
                    except Exception:
                        logger.exception('Cannot parse actor event', extra={'message': message})
        except Exception:
            logger.exception('Error in websocket connection')
            self._connected_to_platform_websocket.set_result(False)
