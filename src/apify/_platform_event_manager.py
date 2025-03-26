from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any, Literal, Union

import websockets.asyncio.client
from pydantic import BaseModel, Discriminator, Field, TypeAdapter
from typing_extensions import Self, Unpack, override

from crawlee.events._event_manager import EventManager, EventManagerOptions
from crawlee.events._local_event_manager import LocalEventManager
from crawlee.events._types import (
    Event,
    EventAbortingData,
    EventExitData,
    EventMigratingData,
    EventPersistStateData,
    EventSystemInfoData,
)

from apify._utils import docs_group
from apify.log import logger

if TYPE_CHECKING:
    from types import TracebackType

    from apify._configuration import Configuration


__all__ = ['EventManager', 'LocalEventManager', 'PlatformEventManager']


@docs_group('Data structures')
class PersistStateEvent(BaseModel):
    name: Literal[Event.PERSIST_STATE]
    data: Annotated[EventPersistStateData, Field(default_factory=lambda: EventPersistStateData(is_migrating=False))]


@docs_group('Data structures')
class SystemInfoEventData(BaseModel):
    mem_avg_bytes: Annotated[float, Field(alias='memAvgBytes')]
    mem_current_bytes: Annotated[float, Field(alias='memCurrentBytes')]
    mem_max_bytes: Annotated[float, Field(alias='memMaxBytes')]
    cpu_avg_usage: Annotated[float, Field(alias='cpuAvgUsage')]
    cpu_max_usage: Annotated[float, Field(alias='cpuMaxUsage')]
    cpu_current_usage: Annotated[float, Field(alias='cpuCurrentUsage')]
    is_cpu_overloaded: Annotated[bool, Field(alias='isCpuOverloaded')]
    created_at: Annotated[datetime, Field(alias='createdAt')]

    def to_crawlee_format(self, dedicated_cpus: float) -> EventSystemInfoData:
        return EventSystemInfoData.model_validate(
            {
                'cpu_info': {
                    'used_ratio': (self.cpu_current_usage / 100) / dedicated_cpus,
                    'created_at': self.created_at,
                },
                'memory_info': {
                    'total_size': self.mem_max_bytes,
                    'current_size': self.mem_current_bytes,
                    'created_at': self.created_at,
                },
            }
        )


@docs_group('Data structures')
class SystemInfoEvent(BaseModel):
    name: Literal[Event.SYSTEM_INFO]
    data: SystemInfoEventData


@docs_group('Data structures')
class MigratingEvent(BaseModel):
    name: Literal[Event.MIGRATING]
    data: Annotated[EventMigratingData, Field(default_factory=EventMigratingData)]


@docs_group('Data structures')
class AbortingEvent(BaseModel):
    name: Literal[Event.ABORTING]
    data: Annotated[EventAbortingData, Field(default_factory=EventAbortingData)]


@docs_group('Data structures')
class ExitEvent(BaseModel):
    name: Literal[Event.EXIT]
    data: Annotated[EventExitData, Field(default_factory=EventExitData)]


@docs_group('Data structures')
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


@docs_group('Data structures')
class DeprecatedEvent(BaseModel):
    name: Literal['cpuInfo']
    data: Annotated[dict[str, Any], Field(default_factory=dict)]


@docs_group('Data structures')
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


event_data_adapter: TypeAdapter[EventMessage | DeprecatedEvent | UnknownEvent] = TypeAdapter(
    Union[
        Annotated[
            EventMessage,
            Discriminator('name'),
        ],
        DeprecatedEvent,
        UnknownEvent,
    ]
)


@docs_group('Classes')
class PlatformEventManager(EventManager):
    """A class for managing Actor events.

    You shouldn't use this class directly,
    but instead use it via the `Actor.on()` and `Actor.off()` methods.
    """

    _platform_events_websocket: websockets.asyncio.client.ClientConnection | None = None
    _process_platform_messages_task: asyncio.Task | None = None
    _send_system_info_interval_task: asyncio.Task | None = None
    _connected_to_platform_websocket: asyncio.Future = asyncio.Future()

    def __init__(self, config: Configuration, **kwargs: Unpack[EventManagerOptions]) -> None:
        """Create an instance of the EventManager.

        Args:
            config: The Actor configuration to be used in this event manager.
            kwargs: Event manager options - forwarded to the base class
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
            self._process_platform_messages_task = asyncio.create_task(
                self._process_platform_messages(self._config.actor_events_ws_url)
            )
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
            async with websockets.asyncio.client.connect(ws_url) as websocket:
                self._platform_events_websocket = websocket
                self._connected_to_platform_websocket.set_result(True)

                async for message in websocket:
                    try:
                        parsed_message = event_data_adapter.validate_json(message)

                        if isinstance(parsed_message, DeprecatedEvent):
                            continue

                        if isinstance(parsed_message, UnknownEvent):
                            logger.info(
                                f'Unknown message received: event_name={parsed_message.name}, '
                                f'event_data={parsed_message.data}'
                            )
                            continue

                        self.emit(
                            event=parsed_message.name,
                            event_data=parsed_message.data
                            if not isinstance(parsed_message.data, SystemInfoEventData)
                            else parsed_message.data.to_crawlee_format(self._config.dedicated_cpus or 1),
                        )

                        if parsed_message.name == Event.MIGRATING:
                            await self._emit_persist_state_event_rec_task.stop()
                            self.emit(event=Event.PERSIST_STATE, event_data=EventPersistStateData(is_migrating=True))
                    except Exception:
                        logger.exception('Cannot parse Actor event', extra={'message': message})
        except Exception:
            logger.exception('Error in websocket connection')
            self._connected_to_platform_websocket.set_result(False)
