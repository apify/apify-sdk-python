from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from crawlee.events._types import (
    Event,
    EventAbortingData,
    EventExitData,
    EventMigratingData,
    EventPersistStateData,
    EventSystemInfoData,
)

from apify._utils import docs_group


@docs_group('Event data')
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


@docs_group('Events')
class PersistStateEvent(BaseModel):
    name: Literal[Event.PERSIST_STATE]
    data: Annotated[EventPersistStateData, Field(default_factory=lambda: EventPersistStateData(is_migrating=False))]


@docs_group('Events')
class SystemInfoEvent(BaseModel):
    name: Literal[Event.SYSTEM_INFO]
    data: SystemInfoEventData


@docs_group('Events')
class MigratingEvent(BaseModel):
    name: Literal[Event.MIGRATING]
    data: Annotated[EventMigratingData, Field(default_factory=EventMigratingData)]


@docs_group('Events')
class AbortingEvent(BaseModel):
    name: Literal[Event.ABORTING]
    data: Annotated[EventAbortingData, Field(default_factory=EventAbortingData)]


@docs_group('Events')
class ExitEvent(BaseModel):
    name: Literal[Event.EXIT]
    data: Annotated[EventExitData, Field(default_factory=EventExitData)]


@docs_group('Events')
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


@docs_group('Events')
class DeprecatedEvent(BaseModel):
    name: Literal['cpuInfo']
    data: Annotated[dict[str, Any], Field(default_factory=dict)]


@docs_group('Events')
class UnknownEvent(BaseModel):
    name: str
    data: Annotated[dict[str, Any], Field(default_factory=dict)]


EventMessage = PersistStateEvent | SystemInfoEvent | MigratingEvent | AbortingEvent | ExitEvent | EventWithoutData
