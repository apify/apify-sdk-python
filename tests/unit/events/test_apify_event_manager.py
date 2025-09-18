from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

import pytest
import websockets
import websockets.asyncio.server

from apify_shared.consts import ActorEnvVars
from crawlee.events._types import Event

from apify import Configuration
from apify.events import ApifyEventManager
from apify.events._types import SystemInfoEventData

if TYPE_CHECKING:
    from collections.abc import Callable


async def test_lifecycle_local(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger='apify')

    async with ApifyEventManager(Configuration()):
        pass

    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.DEBUG
    assert (
        caplog.records[0].message
        == 'APIFY_ACTOR_EVENTS_WS_URL env var not set, no events from Apify platform will be emitted.'
    )


async def test_event_handling_local() -> None:
    config = Configuration.get_global_configuration()

    async with ApifyEventManager(config) as event_manager:
        event_calls = defaultdict(list)

        def on_event(event: Event, id: int | None = None) -> Callable:
            def event_handler(data: Any) -> None:
                nonlocal event_calls
                event_calls[event].append((id, data))

            return event_handler

        handler_system_info = on_event(Event.SYSTEM_INFO)
        dummy_system_info = Mock()
        dummy_system_info_2 = Mock()

        # Basic test with just one handler on event
        # Test adding the handler
        event_manager.on(event=Event.SYSTEM_INFO, listener=handler_system_info)
        event_manager.emit(event=Event.SYSTEM_INFO, event_data=dummy_system_info)
        await asyncio.sleep(0.1)
        assert event_calls[Event.SYSTEM_INFO] == [(None, dummy_system_info)]
        event_calls[Event.SYSTEM_INFO].clear()

        # Test removing the handler
        event_manager.off(event=Event.SYSTEM_INFO, listener=handler_system_info)
        event_manager.emit(event=Event.SYSTEM_INFO, event_data=dummy_system_info_2)
        await asyncio.sleep(0.1)
        assert event_calls[Event.SYSTEM_INFO] == []

        # Complicated test with multiple handlers
        # Add three handlers
        handler_persist_state_1 = on_event(Event.PERSIST_STATE, 1)
        handler_persist_state_2 = on_event(Event.PERSIST_STATE, 2)
        handler_persist_state_3 = on_event(Event.PERSIST_STATE, 3)
        event_manager.on(event=Event.PERSIST_STATE, listener=handler_persist_state_1)
        event_manager.on(event=Event.PERSIST_STATE, listener=handler_persist_state_2)
        event_manager.on(event=Event.PERSIST_STATE, listener=handler_persist_state_3)

        dummy_persist_state = Mock()

        # Test that they all work
        event_manager.emit(event=Event.PERSIST_STATE, event_data=dummy_persist_state)
        await asyncio.sleep(0.1)
        assert set(event_calls[Event.PERSIST_STATE]) == {
            (1, dummy_persist_state),
            (2, dummy_persist_state),
            (3, dummy_persist_state),
        }
        event_calls[Event.PERSIST_STATE].clear()

        # Test that if you remove one, the others stay
        event_manager.off(event=Event.PERSIST_STATE, listener=handler_persist_state_3)
        event_manager.emit(event=Event.PERSIST_STATE, event_data=dummy_persist_state)
        await asyncio.sleep(0.1)
        assert set(event_calls[Event.PERSIST_STATE]) == {
            (1, dummy_persist_state),
            (2, dummy_persist_state),
        }
        event_calls[Event.PERSIST_STATE].clear()

        # Test that removing all in bulk works
        event_manager.off(event=Event.PERSIST_STATE)
        event_manager.emit(event=Event.PERSIST_STATE, event_data=dummy_persist_state)
        await asyncio.sleep(0.1)
        assert event_calls[Event.PERSIST_STATE] == []


async def test_event_async_handling_local() -> None:
    dummy_system_info = Mock()
    config = Configuration.get_global_configuration()

    async with ApifyEventManager(config) as event_manager:
        event_calls = []

        async def event_handler(data: Any) -> None:
            nonlocal event_calls
            await asyncio.sleep(2)
            event_calls.append(data)

        # Test that async event handlers work, and that they don't block the main thread
        event_manager.on(event=Event.SYSTEM_INFO, listener=event_handler)
        event_manager.emit(event=Event.SYSTEM_INFO, event_data=dummy_system_info)
        await asyncio.sleep(1)
        assert event_calls == []
        await asyncio.sleep(2)
        assert event_calls == [dummy_system_info]


async def test_lifecycle_on_platform_without_websocket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ActorEnvVars.EVENTS_WEBSOCKET_URL, 'ws://localhost:56565')
    event_manager = ApifyEventManager(Configuration.get_global_configuration())

    with pytest.raises(RuntimeError, match=r'Error connecting to platform events websocket!'):
        async with event_manager:
            pass


async def test_lifecycle_on_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    connected_ws_clients: set[websockets.asyncio.server.ServerConnection] = set()

    async def handler(websocket: websockets.asyncio.server.ServerConnection) -> None:
        connected_ws_clients.add(websocket)
        try:
            await websocket.wait_closed()
        finally:
            connected_ws_clients.remove(websocket)

    async with websockets.asyncio.server.serve(handler, host='localhost') as ws_server:
        # When you don't specify a port explicitly, the websocket connection is opened on a random free port.
        # We need to find out which port is that.
        port: int = ws_server.sockets[0].getsockname()[1]  # type: ignore[index]
        monkeypatch.setenv(ActorEnvVars.EVENTS_WEBSOCKET_URL, f'ws://localhost:{port}')

        async with ApifyEventManager(Configuration.get_global_configuration()):
            assert len(connected_ws_clients) == 1


async def test_event_handling_on_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    connected_ws_clients: set[websockets.asyncio.server.ServerConnection] = set()

    async def handler(websocket: websockets.asyncio.server.ServerConnection) -> None:
        connected_ws_clients.add(websocket)
        try:
            await websocket.wait_closed()
        finally:
            connected_ws_clients.remove(websocket)

    async def send_platform_event(event_name: Event, data: Any = None) -> None:
        message: dict[str, Any] = {'name': event_name.value}
        if data:
            message['data'] = data

        websockets.broadcast(connected_ws_clients, json.dumps(message))

    async with websockets.asyncio.server.serve(handler, host='localhost') as ws_server:
        # When you don't specify a port explicitly, the websocket connection is opened on a random free port.
        # We need to find out which port is that.
        port: int = ws_server.sockets[0].getsockname()[1]  # type: ignore[index]
        monkeypatch.setenv(ActorEnvVars.EVENTS_WEBSOCKET_URL, f'ws://localhost:{port}')

        dummy_system_info = {
            'memAvgBytes': 19328860.328293584,
            'memCurrentBytes': 65171456,
            'memMaxBytes': 65171456,
            'cpuAvgUsage': 2.0761105633130397,
            'cpuMaxUsage': 53.941134593993326,
            'cpuCurrentUsage': 8.45549815498155,
            'isCpuOverloaded': False,
            'createdAt': '2024-08-09T16:04:16.161Z',
        }
        SystemInfoEventData.model_validate(dummy_system_info)

        async with ApifyEventManager(Configuration.get_global_configuration()) as event_manager:
            event_calls = []

            def listener(data: Any) -> None:
                event_calls.append(json.loads(data.model_dump_json(by_alias=True)) if data else None)

            event_manager.on(event=Event.SYSTEM_INFO, listener=listener)

            # Test sending event with data
            await send_platform_event(Event.SYSTEM_INFO, dummy_system_info)
            await asyncio.sleep(0.1)
            assert len(event_calls) == 1
            assert event_calls[0] is not None
            assert event_calls[0]['cpuInfo']['usedRatio'] == 0.0845549815498155
            event_calls.clear()
