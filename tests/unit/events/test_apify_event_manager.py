from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import defaultdict
from datetime import timedelta
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
    from collections.abc import AsyncGenerator, Callable


@contextlib.asynccontextmanager
async def _platform_ws_server(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[tuple[set[websockets.asyncio.server.ServerConnection], asyncio.Event]]:
    """Create a local WebSocket server that simulates Apify platform events.

    Binds explicitly to ``127.0.0.1`` instead of ``localhost`` so that only a
    single IPv4 socket is created.  On Windows, ``localhost`` resolves to both
    ``127.0.0.1`` *and* ``::1``, and the OS may assign **different** random
    ports to each address — causing the client to connect to the wrong port.

    Yields a ``(connected_ws_clients, client_connected_event)`` tuple.  After
    opening an `ApifyEventManager`, ``await client_connected_event.wait()``
    before sending any messages to guarantee the server handler has registered
    the connection.
    """
    connected_ws_clients: set[websockets.asyncio.server.ServerConnection] = set()
    client_connected = asyncio.Event()

    async def handler(websocket: websockets.asyncio.server.ServerConnection) -> None:
        connected_ws_clients.add(websocket)
        client_connected.set()
        try:
            await websocket.wait_closed()
        finally:
            connected_ws_clients.remove(websocket)

    async with websockets.asyncio.server.serve(handler, host='127.0.0.1') as ws_server:
        port: int = ws_server.sockets[0].getsockname()[1]
        monkeypatch.setenv(ActorEnvVars.EVENTS_WEBSOCKET_URL, f'ws://127.0.0.1:{port}')
        yield connected_ws_clients, client_connected


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
    async with (
        _platform_ws_server(monkeypatch) as (connected_ws_clients, client_connected),
        ApifyEventManager(Configuration.get_global_configuration()),
    ):
        await client_connected.wait()
        assert len(connected_ws_clients) == 1


async def test_event_handling_on_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    async with _platform_ws_server(monkeypatch) as (connected_ws_clients, client_connected):

        async def send_platform_event(event_name: Event, data: Any = None) -> None:
            message: dict[str, Any] = {'name': event_name.value}
            if data:
                message['data'] = data

            websockets.broadcast(connected_ws_clients, json.dumps(message))

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
            await client_connected.wait()
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


async def test_event_listener_removal_stops_counting() -> None:
    """Test that removing an event listener stops it from receiving further events."""
    config = Configuration.get_global_configuration()

    async with ApifyEventManager(config, persist_state_interval=timedelta(milliseconds=500)) as event_manager:
        persist_state_counter = 0

        async def handler(_data: Any) -> None:
            nonlocal persist_state_counter
            persist_state_counter += 1

        event_manager.on(event=Event.PERSIST_STATE, listener=handler)
        await asyncio.sleep(1.5)
        first_count = persist_state_counter
        assert first_count > 0

        event_manager.off(event=Event.PERSIST_STATE, listener=handler)
        persist_state_counter = 0
        await asyncio.sleep(1.5)
        assert persist_state_counter == 0


async def test_deprecated_event_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that deprecated events (like CPU_INFO) are silently skipped."""
    async with (
        _platform_ws_server(monkeypatch) as (connected_ws_clients, client_connected),
        ApifyEventManager(Configuration.get_global_configuration()) as event_manager,
    ):
        await client_connected.wait()
        event_calls: list[Any] = []

        def listener(data: Any) -> None:
            event_calls.append(data)

        event_manager.on(event=Event.SYSTEM_INFO, listener=listener)

        # Send a deprecated event (cpuInfo is deprecated)
        deprecated_message = json.dumps({'name': 'cpuInfo', 'data': {}})
        websockets.broadcast(connected_ws_clients, deprecated_message)
        await asyncio.sleep(0.2)

        # No events should have been emitted
        assert len(event_calls) == 0


async def test_unknown_event_is_logged(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """Test that unknown events are logged and not emitted."""
    caplog.set_level(logging.INFO, logger='apify')
    async with (
        _platform_ws_server(monkeypatch) as (connected_ws_clients, client_connected),
        ApifyEventManager(Configuration.get_global_configuration()),
    ):
        await client_connected.wait()

        # Send an unknown event
        unknown_message = json.dumps({'name': 'totallyNewEvent2099', 'data': {'foo': 'bar'}})
        websockets.broadcast(connected_ws_clients, unknown_message)
        await asyncio.sleep(0.2)

        assert 'Unknown message received' in caplog.text
        assert 'totallyNewEvent2099' in caplog.text


async def test_migrating_event_triggers_persist_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that a MIGRATING event triggers a PERSIST_STATE event with is_migrating=True."""
    async with (
        _platform_ws_server(monkeypatch) as (connected_ws_clients, client_connected),
        ApifyEventManager(Configuration.get_global_configuration()) as event_manager,
    ):
        await client_connected.wait()
        persist_calls: list[Any] = []
        migrating_calls: list[Any] = []

        def persist_listener(data: Any) -> None:
            persist_calls.append(data)

        def migrating_listener(data: Any) -> None:
            migrating_calls.append(data)

        event_manager.on(event=Event.PERSIST_STATE, listener=persist_listener)
        event_manager.on(event=Event.MIGRATING, listener=migrating_listener)

        # Clear any initial persist state events
        await asyncio.sleep(0.2)
        persist_calls.clear()

        # Send migrating event
        migrating_message = json.dumps({'name': 'migrating'})
        websockets.broadcast(connected_ws_clients, migrating_message)
        await asyncio.sleep(0.2)

        assert len(migrating_calls) == 1
        # MIGRATING should also trigger a PERSIST_STATE with is_migrating=True
        migration_persist_events = [c for c in persist_calls if hasattr(c, 'is_migrating') and c.is_migrating]
        assert len(migration_persist_events) >= 1


async def test_malformed_message_logs_exception(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that malformed websocket messages are logged and don't crash the event manager."""
    async with (
        _platform_ws_server(monkeypatch) as (connected_ws_clients, client_connected),
        ApifyEventManager(Configuration.get_global_configuration()),
    ):
        await client_connected.wait()

        # Send malformed message
        websockets.broadcast(connected_ws_clients, 'this is not valid json{{{')
        await asyncio.sleep(0.2)

        assert 'Cannot parse Actor event' in caplog.text
