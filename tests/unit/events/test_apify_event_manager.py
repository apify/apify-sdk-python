from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import socket
import types
from collections import defaultdict
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

import pytest
import websockets
import websockets.asyncio.server

from crawlee.events._types import Event

from ..._utils import poll_until_condition
from apify import Configuration
from apify._consts import ActorEnvVars
from apify.events import ApifyEventManager
from apify.events._types import SystemInfoEventData

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable


DUMMY_SYSTEM_INFO = {
    'memAvgBytes': 19328860.328293584,
    'memCurrentBytes': 65171456,
    'memMaxBytes': 65171456,
    'cpuAvgUsage': 2.0761105633130397,
    'cpuMaxUsage': 53.941134593993326,
    'cpuCurrentUsage': 8.45549815498155,
    'isCpuOverloaded': False,
    'createdAt': '2024-08-09T16:04:16.161Z',
}


@contextlib.asynccontextmanager
async def _platform_ws_server(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[tuple[set[websockets.asyncio.server.ServerConnection], asyncio.Event]]:
    """Create a local WebSocket server that simulates Apify platform events.

    Binds explicitly to `127.0.0.1` instead of `localhost` so that only a single IPv4 socket is created. On Windows,
    `localhost` resolves to both `127.0.0.1` *and* `::1`, and the OS may assign **different** random ports to each
    address — causing the client to connect to the wrong port.

    Yields a `(connected_ws_clients, client_connected_event)` tuple. After opening an `ApifyEventManager`,
    `await client_connected_event.wait()` before sending any messages to guarantee the server handler has registered
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


@contextlib.asynccontextmanager
async def _restartable_ws_server(
    monkeypatch: pytest.MonkeyPatch,
    *,
    on_connect: Callable[[websockets.asyncio.server.ServerConnection], Awaitable[None]] | None = None,
) -> AsyncGenerator[Any]:
    """A local `127.0.0.1` WebSocket server that can be stopped/restarted and counts connection attempts.

    Binds to a fixed free port (reserved up front) so a restart can reuse the same address, letting a test simulate the
    platform server going away and coming back. Yields a control namespace with `live_clients`, a re-armable
    `client_connected` event, a cumulative `attempts()` counter, and `stop()` / `start()` coroutines. Pass `on_connect`
    to take over a freshly accepted connection (e.g. immediately close it with a chosen code).
    """
    # Reserve a fixed free port so a restart can re-serve on the same address.
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
    probe.close()

    live_clients: set[websockets.asyncio.server.ServerConnection] = set()
    client_connected = asyncio.Event()
    attempts = 0
    server_holder: dict[str, Any] = {'srv': None}

    async def handler(websocket: websockets.asyncio.server.ServerConnection) -> None:
        nonlocal attempts
        attempts += 1
        if on_connect is not None:
            await on_connect(websocket)
            return
        live_clients.add(websocket)
        client_connected.set()
        try:
            await websocket.wait_closed()
        finally:
            live_clients.discard(websocket)

    async def _serve() -> None:
        server_holder['srv'] = await websockets.asyncio.server.serve(handler, host='127.0.0.1', port=port)

    async def stop() -> None:
        srv = server_holder['srv']
        if srv is not None:
            srv.close()
            await srv.wait_closed()
            server_holder['srv'] = None
        # Drop any live connection so the client is forced into reconnect mode.
        for websocket in list(live_clients):
            await websocket.close()

    async def start() -> None:
        await asyncio.sleep(0.3)  # Give the OS a moment to release the port before re-serving.
        await _serve()

    monkeypatch.setenv(ActorEnvVars.EVENTS_WEBSOCKET_URL, f'ws://127.0.0.1:{port}')
    await _serve()
    try:
        yield types.SimpleNamespace(
            live_clients=live_clients,
            client_connected=client_connected,
            attempts=lambda: attempts,
            stop=stop,
            start=start,
        )
    finally:
        await stop()


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
        await poll_until_condition(lambda: bool(event_calls[Event.SYSTEM_INFO]), poll_interval=0.05)
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
        await poll_until_condition(lambda: len(event_calls[Event.PERSIST_STATE]) >= 3, poll_interval=0.05)
        assert set(event_calls[Event.PERSIST_STATE]) == {
            (1, dummy_persist_state),
            (2, dummy_persist_state),
            (3, dummy_persist_state),
        }
        event_calls[Event.PERSIST_STATE].clear()

        # Test that if you remove one, the others stay
        event_manager.off(event=Event.PERSIST_STATE, listener=handler_persist_state_3)
        event_manager.emit(event=Event.PERSIST_STATE, event_data=dummy_persist_state)
        await poll_until_condition(lambda: len(event_calls[Event.PERSIST_STATE]) >= 2, poll_interval=0.05)
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
    """Test that a failed websocket connection raises and also exits the parent's recurring persist state task."""
    monkeypatch.setenv(ActorEnvVars.EVENTS_WEBSOCKET_URL, 'ws://localhost:56565')
    event_manager = ApifyEventManager(Configuration.get_global_configuration())

    with pytest.raises(RuntimeError, match=r'Error connecting to platform events websocket!'):
        async with event_manager:
            pass

    assert event_manager.active is False
    persist_state_task = event_manager._emit_persist_state_event_rec_task.task
    assert persist_state_task is None or persist_state_task.done()


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

        SystemInfoEventData.model_validate(DUMMY_SYSTEM_INFO)

        async with ApifyEventManager(Configuration.get_global_configuration()) as event_manager:
            await client_connected.wait()
            event_calls = []

            def listener(data: Any) -> None:
                event_calls.append(json.loads(data.model_dump_json(by_alias=True)) if data else None)

            event_manager.on(event=Event.SYSTEM_INFO, listener=listener)

            # Test sending event with data
            await send_platform_event(Event.SYSTEM_INFO, DUMMY_SYSTEM_INFO)
            await poll_until_condition(lambda: len(event_calls) == 1, poll_interval=0.05)
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
        # Wait until at least one PERSIST_STATE event is handled (the persist interval is 500 ms).
        await poll_until_condition(lambda: persist_state_counter > 0, poll_interval=0.05)
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
        await poll_until_condition(lambda: 'Unknown message received' in caplog.text, poll_interval=0.05)

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
        await poll_until_condition(
            lambda: bool(migrating_calls) and any(getattr(c, 'is_migrating', False) for c in persist_calls),
            poll_interval=0.05,
        )

        assert len(migrating_calls) == 1
        # MIGRATING should also trigger a PERSIST_STATE with is_migrating=True
        migration_persist_events = [c for c in persist_calls if hasattr(c, 'is_migrating') and c.is_migrating]
        assert len(migration_persist_events) >= 1


@pytest.mark.parametrize(
    ('close_code', 'expected_log'),
    [
        pytest.param(1000, 'Connection to platform events websocket was closed (code=1000', id='graceful_close'),
        pytest.param(1011, 'Connection to platform events websocket was lost (code=1011', id='abnormal_close'),
    ],
)
async def test_websocket_reconnects_after_connection_drop(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, close_code: int, expected_log: str
) -> None:
    """Test that the event manager logs a websocket drop, reconnects, and keeps receiving platform events.

    Also a regression test for the resolved `_connected_to_platform_websocket` future: a mid-stream disconnect
    must not kill the message-processing task with `InvalidStateError`.
    """
    caplog.set_level(logging.INFO, logger='apify')
    async with (
        _platform_ws_server(monkeypatch) as (connected_ws_clients, client_connected),
        ApifyEventManager(Configuration.get_global_configuration()) as event_manager,
    ):
        await client_connected.wait()
        assert len(connected_ws_clients) == 1

        event_calls: list[Any] = []
        event_manager.on(event=Event.SYSTEM_INFO, listener=event_calls.append)

        # Drop the connection from the server side and wait for the client to reconnect.
        client_connected.clear()
        for ws in list(connected_ws_clients):
            await ws.close(code=close_code, reason='Simulated connection drop')
        await asyncio.wait_for(client_connected.wait(), timeout=10)
        # Poll because the old server-side handler may not have deregistered its connection yet.
        await poll_until_condition(lambda: len(connected_ws_clients) == 1, poll_interval=0.05)
        assert len(connected_ws_clients) == 1

        # The message-processing task must have survived the drop.
        task = event_manager._process_platform_messages_task
        assert task is not None
        assert not task.done()

        # Events sent over the new connection must still be emitted.
        websockets.broadcast(connected_ws_clients, json.dumps({'name': 'systemInfo', 'data': DUMMY_SYSTEM_INFO}))
        await poll_until_condition(lambda: len(event_calls) == 1, poll_interval=0.05)
        assert len(event_calls) == 1

        # Both the drop and the successful reconnect must be logged.
        assert expected_log in caplog.text
        assert 'Reconnected to the platform events websocket.' in caplog.text


async def test_non_retryable_close_stops_reconnecting(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that a non-retryable close code (1008) stops reconnection instead of looping forever."""
    caplog.set_level(logging.ERROR, logger='apify')

    async def close_with_policy_violation(websocket: websockets.asyncio.server.ServerConnection) -> None:
        await websocket.close(code=1008, reason='policy violation')

    async with (
        _restartable_ws_server(monkeypatch, on_connect=close_with_policy_violation) as server,
        ApifyEventManager(Configuration.get_global_configuration()) as event_manager,
    ):
        task = event_manager._process_platform_messages_task
        assert task is not None

        # After a non-retryable close the processing task must give up rather than reconnect forever.
        await poll_until_condition(task.done, poll_interval=0.05)
        assert task.done()
        assert server.attempts() <= 5, f'reconnected after a non-retryable close: {server.attempts()} attempts'

    assert 'non-retryable code' in caplog.text


async def test_rapid_retryable_close_backs_off(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that repeated retryable closes are retried with backoff instead of a tight reconnect loop."""
    caplog.set_level(logging.WARNING, logger='apify')

    async def close_with_internal_error(websocket: websockets.asyncio.server.ServerConnection) -> None:
        await websocket.close(code=1011, reason='internal error')

    async with (
        _restartable_ws_server(monkeypatch, on_connect=close_with_internal_error) as server,
        ApifyEventManager(Configuration.get_global_configuration()) as event_manager,
    ):
        task = event_manager._process_platform_messages_task
        assert task is not None

        # Without backoff a tight loop would make thousands of attempts in this window; backoff keeps it tiny.
        await asyncio.sleep(2)
        assert not task.done()
        attempts = server.attempts()

    assert 0 < attempts <= 15, f'client busy-looped on a retryable close: {attempts} attempts in 2s'
    assert 'was lost (code=1011' in caplog.text


async def test_rapid_retryable_close_after_event_backs_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that a server that delivers an event before each retryable close is still retried with backoff."""

    async def send_event_then_close(websocket: websockets.asyncio.server.ServerConnection) -> None:
        await websocket.send(json.dumps({'name': 'systemInfo', 'data': DUMMY_SYSTEM_INFO}))
        await websocket.close(code=1011, reason='internal error')

    async with (
        _restartable_ws_server(monkeypatch, on_connect=send_event_then_close) as server,
        ApifyEventManager(Configuration.get_global_configuration()) as event_manager,
    ):
        task = event_manager._process_platform_messages_task
        assert task is not None

        # A short-lived connection must back off even though it delivered an event, or it would busy-loop.
        await asyncio.sleep(2)
        assert not task.done()
        attempts = server.attempts()

    assert 0 < attempts <= 15, f'client busy-looped after a message-bearing close: {attempts} attempts in 2s'


async def test_reconnects_after_server_becomes_unreachable(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that the client survives a server outage, keeps retrying, and resumes events once the server returns."""
    caplog.set_level(logging.INFO, logger='apify')

    async with (
        _restartable_ws_server(monkeypatch) as server,
        ApifyEventManager(Configuration.get_global_configuration()) as event_manager,
    ):
        await asyncio.wait_for(server.client_connected.wait(), timeout=10)
        assert len(server.live_clients) == 1

        event_calls: list[Any] = []
        event_manager.on(event=Event.SYSTEM_INFO, listener=event_calls.append)

        # Take the server down and drop the live connection: every reconnect attempt now hits connection-refused.
        server.client_connected.clear()
        await server.stop()
        task = event_manager._process_platform_messages_task
        assert task is not None

        # During the outage the task must keep retrying instead of crashing or exiting.
        await asyncio.sleep(1)
        assert not task.done()

        # Bring the server back on the same port; the client must reconnect within a bounded time.
        await server.start()
        await asyncio.wait_for(server.client_connected.wait(), timeout=10)
        await poll_until_condition(lambda: len(server.live_clients) == 1, poll_interval=0.05)
        assert len(server.live_clients) == 1

        # Events sent over the recovered connection must still be delivered.
        websockets.broadcast(server.live_clients, json.dumps({'name': 'systemInfo', 'data': DUMMY_SYSTEM_INFO}))
        await poll_until_condition(lambda: len(event_calls) == 1, poll_interval=0.05)
        assert len(event_calls) == 1

    assert 'Reconnected to the platform events websocket.' in caplog.text


async def test_shutdown_during_reconnect_backoff_is_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that exiting the event manager while it is mid-reconnect (server down) shuts down cleanly."""
    async with _restartable_ws_server(monkeypatch) as server:
        event_manager = ApifyEventManager(Configuration.get_global_configuration())
        async with event_manager:
            await asyncio.wait_for(server.client_connected.wait(), timeout=10)
            assert len(server.live_clients) == 1

            # Force the client into reconnect/backoff: server down, live connection dropped.
            server.client_connected.clear()
            await server.stop()
            task = event_manager._process_platform_messages_task
            assert task is not None
            await asyncio.sleep(0.5)
            assert not task.done()
            # __aexit__ runs here, while the client is between reconnect attempts.

    # The processing task must be finished and cancelled, not crashed with a stray error.
    assert task.done()
    assert task.cancelled() or task.exception() is None
    assert event_manager.active is False
    # The parent recurring persist-state task must be stopped too, mirroring the failed-connect lifecycle test.
    persist_state_task = event_manager._emit_persist_state_event_rec_task.task
    assert persist_state_task is None or persist_state_task.done()


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
        await poll_until_condition(lambda: 'Cannot parse Actor event' in caplog.text, poll_interval=0.05)

        assert 'Cannot parse Actor event' in caplog.text
