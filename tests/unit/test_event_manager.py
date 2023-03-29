import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import Any, Callable, Dict, Optional, Set

import pytest
import websockets
import websockets.server

from apify.config import Configuration
from apify.consts import ActorEventTypes, ApifyEnvVars
from apify.event_manager import EventManager


class TestEventManagerLocal:
    async def test_lifecycle_local(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.DEBUG)

        config = Configuration()
        event_manager = EventManager(config)

        await event_manager.init()
        assert event_manager._initialized is True

        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.DEBUG
        assert caplog.records[0].message == 'APIFY_ACTOR_EVENTS_WS_URL env var not set, no events from Apify platform will be emitted.'

        with pytest.raises(RuntimeError, match='EventManager was already initialized!'):
            await event_manager.init()

        await event_manager.close()

        with pytest.raises(RuntimeError, match='EventManager was not initialized!'):
            await event_manager.close()

        assert event_manager._initialized is False

    async def test_event_handling_local(self) -> None:
        config = Configuration()
        event_manager = EventManager(config)

        await event_manager.init()

        event_calls = defaultdict(list)

        def on_event(event: ActorEventTypes, id: Optional[int] = None) -> Callable:
            def event_handler(data: Any) -> None:
                nonlocal event_calls
                event_calls[event].append((id, data))
            return event_handler

        handler_system_info = on_event(ActorEventTypes.SYSTEM_INFO)

        # Basic test with just one handler on event
        # Test adding the handler
        event_manager.on(ActorEventTypes.SYSTEM_INFO, handler_system_info)
        event_manager.emit(ActorEventTypes.SYSTEM_INFO, 'DUMMY_SYSTEM_INFO')
        await asyncio.sleep(0.1)
        assert event_calls[ActorEventTypes.SYSTEM_INFO] == [(None, 'DUMMY_SYSTEM_INFO')]
        event_calls[ActorEventTypes.SYSTEM_INFO].clear()

        # Test removing the handler
        event_manager.off(ActorEventTypes.SYSTEM_INFO, handler_system_info)
        event_manager.emit(ActorEventTypes.SYSTEM_INFO, 'DUMMY_SYSTEM_INFO_2')
        await asyncio.sleep(0.1)
        assert event_calls[ActorEventTypes.SYSTEM_INFO] == []

        # Complicated test with multiple handlers
        # Add three handlers
        handler_persist_state_1 = on_event(ActorEventTypes.PERSIST_STATE, 1)
        handler_persist_state_2 = on_event(ActorEventTypes.PERSIST_STATE, 2)
        handler_persist_state_3 = on_event(ActorEventTypes.PERSIST_STATE, 3)
        event_manager.on(ActorEventTypes.PERSIST_STATE, handler_persist_state_1)
        event_manager.on(ActorEventTypes.PERSIST_STATE, handler_persist_state_2)
        event_manager.on(ActorEventTypes.PERSIST_STATE, handler_persist_state_3)

        # Test that they all work, and that they're called in order
        event_manager.emit(ActorEventTypes.PERSIST_STATE, 'DUMMY_PERSIST_STATE')
        await asyncio.sleep(0.1)
        assert event_calls[ActorEventTypes.PERSIST_STATE] == [
            (1, 'DUMMY_PERSIST_STATE'),
            (2, 'DUMMY_PERSIST_STATE'),
            (3, 'DUMMY_PERSIST_STATE'),
        ]
        event_calls[ActorEventTypes.PERSIST_STATE].clear()

        # Test that if you remove one, the others stay
        event_manager.off(ActorEventTypes.PERSIST_STATE, handler_persist_state_3)
        event_manager.emit(ActorEventTypes.PERSIST_STATE, 'DUMMY_PERSIST_STATE')
        await asyncio.sleep(0.1)
        assert event_calls[ActorEventTypes.PERSIST_STATE] == [
            (1, 'DUMMY_PERSIST_STATE'),
            (2, 'DUMMY_PERSIST_STATE'),
        ]
        event_calls[ActorEventTypes.PERSIST_STATE].clear()

        # Test that removing all in bulk works
        event_manager.off(ActorEventTypes.PERSIST_STATE)
        event_manager.emit(ActorEventTypes.PERSIST_STATE, 'DUMMY_PERSIST_STATE')
        await asyncio.sleep(0.1)
        assert event_calls[ActorEventTypes.PERSIST_STATE] == []

        await event_manager.close()

    async def test_event_handler_argument_counts_local(self) -> None:
        config = Configuration()
        event_manager = EventManager(config)

        await event_manager.init()

        event_calls = []

        def sync_no_arguments() -> None:
            nonlocal event_calls
            event_calls.append(('sync_no_arguments', None))

        async def async_no_arguments() -> None:
            nonlocal event_calls
            event_calls.append(('async_no_arguments', None))

        def sync_one_argument(event_data: Any) -> None:
            nonlocal event_calls
            event_calls.append(('sync_one_argument', event_data))

        async def async_one_argument(event_data: Any) -> None:
            nonlocal event_calls
            event_calls.append(('async_one_argument', event_data))

        def sync_two_arguments(_arg1: Any, _arg2: Any) -> None:
            pass

        async def async_two_arguments(_arg1: Any, _arg2: Any) -> None:
            pass

        def sync_two_arguments_one_default(event_data: Any, _arg2: Any = 'default_value') -> None:
            nonlocal event_calls
            event_calls.append(('sync_two_arguments_one_default', event_data))

        async def async_two_arguments_one_default(event_data: Any, _arg2: Any = 'default_value') -> None:
            nonlocal event_calls
            event_calls.append(('async_two_arguments_one_default', event_data))

        event_manager.on(ActorEventTypes.SYSTEM_INFO, sync_no_arguments)
        event_manager.on(ActorEventTypes.SYSTEM_INFO, async_no_arguments)
        event_manager.on(ActorEventTypes.SYSTEM_INFO, sync_one_argument)
        event_manager.on(ActorEventTypes.SYSTEM_INFO, async_one_argument)
        event_manager.on(ActorEventTypes.SYSTEM_INFO, sync_two_arguments_one_default)
        event_manager.on(ActorEventTypes.SYSTEM_INFO, async_two_arguments_one_default)

        # built-in functions should work too
        event_manager.on(ActorEventTypes.SYSTEM_INFO, print)

        with pytest.raises(ValueError, match='The "listener" argument must be a callable which accepts 0 or 1 arguments!'):
            event_manager.on(ActorEventTypes.SYSTEM_INFO, sync_two_arguments)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match='The "listener" argument must be a callable which accepts 0 or 1 arguments!'):
            event_manager.on(ActorEventTypes.SYSTEM_INFO, async_two_arguments)  # type: ignore[arg-type]

        event_manager.emit(ActorEventTypes.SYSTEM_INFO, 'DUMMY_SYSTEM_INFO')
        await asyncio.sleep(0.1)

        assert len(event_calls) == 6
        assert ('sync_no_arguments', None) in event_calls
        assert ('async_no_arguments', None) in event_calls
        assert ('sync_one_argument', 'DUMMY_SYSTEM_INFO') in event_calls
        assert ('async_one_argument', 'DUMMY_SYSTEM_INFO') in event_calls
        assert ('sync_two_arguments_one_default', 'DUMMY_SYSTEM_INFO') in event_calls
        assert ('async_two_arguments_one_default', 'DUMMY_SYSTEM_INFO') in event_calls

    async def test_event_async_handling_local(self) -> None:
        config = Configuration()
        event_manager = EventManager(config)

        await event_manager.init()

        event_calls = []

        async def event_handler(data: Any) -> None:
            nonlocal event_calls
            await asyncio.sleep(2)
            event_calls.append(data)

        # Test that async event handlers work, and that they don't block the main thread
        event_manager.on(ActorEventTypes.SYSTEM_INFO, event_handler)
        event_manager.emit(ActorEventTypes.SYSTEM_INFO, 'DUMMY_SYSTEM_INFO')
        await asyncio.sleep(1)
        assert event_calls == []
        await asyncio.sleep(2)
        assert event_calls == ['DUMMY_SYSTEM_INFO']

        await event_manager.close()

    async def test_wait_for_all_listeners_to_complete(self, caplog: pytest.LogCaptureFixture) -> None:
        config = Configuration()
        event_manager = EventManager(config)

        await event_manager.init()

        event_calls = []

        def on_event(sleep_secs: Optional[int] = None) -> Callable:
            async def event_handler(data: Any) -> None:
                nonlocal event_calls
                if sleep_secs:
                    await asyncio.sleep(sleep_secs)
                event_calls.append(data)
            return event_handler

        # Create three handlers, all with a different sleep time, and add them
        handler_1 = on_event(1)
        handler_2 = on_event(2)
        handler_3 = on_event(3)
        event_manager.on(ActorEventTypes.SYSTEM_INFO, handler_1)
        event_manager.on(ActorEventTypes.SYSTEM_INFO, handler_2)
        event_manager.on(ActorEventTypes.SYSTEM_INFO, handler_3)

        # Emit the event, record the emitting time
        emmitted_at = time.perf_counter()
        event_manager.emit(ActorEventTypes.SYSTEM_INFO, 'DUMMY_SYSTEM_INFO')
        await asyncio.sleep(0.1)

        # Wait for all of the handlers to finish and check that it took the right amount of time
        await event_manager.wait_for_all_listeners_to_complete()

        duration = time.perf_counter() - emmitted_at
        assert duration > 2.8
        assert duration < 4
        assert event_calls == ['DUMMY_SYSTEM_INFO', 'DUMMY_SYSTEM_INFO', 'DUMMY_SYSTEM_INFO']
        event_calls.clear()

        # Emit the event again, record the emitting time
        emmitted_at = time.perf_counter()
        event_manager.emit(ActorEventTypes.SYSTEM_INFO, 'DUMMY_SYSTEM_INFO')
        await asyncio.sleep(0.1)

        # Wait for all of the handlers to finish and check that it took the right amount of time
        # This time add a timeout so that only 1 handler should have time to finish
        await event_manager.wait_for_all_listeners_to_complete(timeout_secs=1.5)

        duration = time.perf_counter() - emmitted_at
        assert duration > 1.3
        assert duration < 2
        assert event_calls == ['DUMMY_SYSTEM_INFO']
        await asyncio.sleep(2)
        assert event_calls == ['DUMMY_SYSTEM_INFO']
        event_calls.clear()

        assert caplog.records[0].levelno == logging.WARNING
        assert caplog.records[0].message == 'Timed out waiting for event listeners to complete, unfinished event listeners will be canceled'

        # Emit the event again, test that closing the event manager waits for the handlers to complete
        emmitted_at = time.perf_counter()
        event_manager.emit(ActorEventTypes.SYSTEM_INFO, 'DUMMY_SYSTEM_INFO')
        await asyncio.sleep(0.1)

        await event_manager.close()

        duration = time.perf_counter() - emmitted_at
        assert duration > 2.8
        assert duration < 4
        assert event_calls == ['DUMMY_SYSTEM_INFO', 'DUMMY_SYSTEM_INFO', 'DUMMY_SYSTEM_INFO']


class TestEventManagerOnPlatform:
    async def test_lifecycle_on_platform_without_websocket(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ApifyEnvVars.ACTOR_EVENTS_WS_URL, 'ws://localhost:56565')

        config = Configuration()
        event_manager = EventManager(config)

        with pytest.raises(RuntimeError, match='Error connecting to platform events websocket!'):
            await event_manager.init()

        assert event_manager._initialized is False

    async def test_lifecycle_on_platform(self, monkeypatch: pytest.MonkeyPatch) -> None:
        connected_ws_clients: Set[websockets.server.WebSocketServerProtocol] = set()

        async def handler(websocket: websockets.server.WebSocketServerProtocol) -> None:
            connected_ws_clients.add(websocket)
            try:
                await websocket.wait_closed()
            finally:
                connected_ws_clients.remove(websocket)

        async with websockets.server.serve(handler, host='localhost') as ws_server:
            # When you don't specify a port explicitly, the websocket connection is opened on a random free port.
            # We need to find out which port is that.
            port: int = ws_server.sockets[0].getsockname()[1]  # type: ignore[index]
            monkeypatch.setenv(ApifyEnvVars.ACTOR_EVENTS_WS_URL, f'ws://localhost:{port}')

            config = Configuration()
            event_manager = EventManager(config)

            await event_manager.init()
            assert event_manager._initialized is True

            assert len(connected_ws_clients) == 1

            await event_manager.close()

            assert event_manager._initialized is False

    async def test_event_handling_on_platform(self, monkeypatch: pytest.MonkeyPatch) -> None:
        connected_ws_clients: Set[websockets.server.WebSocketServerProtocol] = set()

        async def handler(websocket: websockets.server.WebSocketServerProtocol) -> None:
            connected_ws_clients.add(websocket)
            try:
                await websocket.wait_closed()
            finally:
                connected_ws_clients.remove(websocket)

        async def send_platform_event(event_name: ActorEventTypes, data: Any = None) -> None:
            message: Dict[str, Any] = {'name': event_name}
            if data:
                message['data'] = data

            websockets.broadcast(connected_ws_clients, json.dumps(message))  # type: ignore[attr-defined]

        async with websockets.server.serve(handler, host='localhost') as ws_server:
            # When you don't specify a port explicitly, the websocket connection is opened on a random free port.
            # We need to find out which port is that.
            port: int = ws_server.sockets[0].getsockname()[1]  # type: ignore[index]
            monkeypatch.setenv(ApifyEnvVars.ACTOR_EVENTS_WS_URL, f'ws://localhost:{port}')

            config = Configuration()
            event_manager = EventManager(config)

            await event_manager.init()

            event_calls = []
            event_manager.on(ActorEventTypes.SYSTEM_INFO, lambda data: event_calls.append(data))

            # Test sending event with data
            await send_platform_event(ActorEventTypes.SYSTEM_INFO, 'DUMMY_SYSTEM_INFO')
            await asyncio.sleep(0.1)
            assert event_calls == ['DUMMY_SYSTEM_INFO']
            event_calls.clear()

            # Test sending event without data
            await send_platform_event(ActorEventTypes.SYSTEM_INFO)
            await asyncio.sleep(0.1)
            assert event_calls == [None]

            await event_manager.close()
