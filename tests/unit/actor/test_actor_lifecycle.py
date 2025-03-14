from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, cast
from unittest.mock import AsyncMock, Mock

import pytest
import websockets.asyncio.server

from apify_shared.consts import ActorEnvVars, ApifyEnvVars
from crawlee.events._types import Event, EventPersistStateData

import apify._actor
from apify import Actor
from apify._actor import _ActorType

if TYPE_CHECKING:
    from lazy_object_proxy import Proxy


async def test_actor_properly_init_with_async() -> None:
    async with Actor:
        assert cast('Proxy', apify._actor.Actor).__wrapped__ is not None
        assert cast('Proxy', apify._actor.Actor).__wrapped__._is_initialized
    assert not cast('Proxy', apify._actor.Actor).__wrapped__._is_initialized


async def test_actor_init() -> None:
    my_actor = _ActorType()

    await my_actor.init()
    assert my_actor._is_initialized is True

    await my_actor.exit()
    assert my_actor._is_initialized is False


async def test_double_init_raises_error(prepare_test_env: Callable) -> None:
    async with Actor:
        assert Actor._is_initialized
        with pytest.raises(RuntimeError):
            await Actor.init()

    prepare_test_env()

    async with Actor() as actor:
        assert actor._is_initialized
        with pytest.raises(RuntimeError):
            await actor.init()

    prepare_test_env()

    async with _ActorType() as actor:
        assert actor._is_initialized
        with pytest.raises(RuntimeError):
            await actor.init()


async def test_actor_exits_cleanly_with_events(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ApifyEnvVars.SYSTEM_INFO_INTERVAL_MILLIS, '100')
    monkeypatch.setenv(ApifyEnvVars.PERSIST_STATE_INTERVAL_MILLIS, '100')
    on_persist = []
    on_system_info = []

    def on_event(event_type: Event) -> Callable:
        nonlocal on_persist
        nonlocal on_system_info
        if event_type == Event.PERSIST_STATE:
            return lambda data: on_persist.append(data)
        if event_type == Event.SYSTEM_INFO:
            return lambda data: on_system_info.append(data)
        return lambda data: print(data)

    my_actor = _ActorType()
    async with my_actor:
        assert my_actor._is_initialized
        my_actor.on(Event.PERSIST_STATE, on_event(Event.PERSIST_STATE))
        my_actor.on(Event.SYSTEM_INFO, on_event(Event.SYSTEM_INFO))
        await asyncio.sleep(1)

    on_persist_count = len(on_persist)
    on_system_info_count = len(on_system_info)
    assert on_persist_count != 0
    assert on_system_info_count != 0

    # Check if events stopped emitting.
    await asyncio.sleep(0.2)
    assert on_persist_count == len(on_persist)
    assert on_system_info_count == len(on_system_info)


async def test_exit_without_init_raises_error() -> None:
    with pytest.raises(RuntimeError):
        await Actor.exit()


async def test_actor_fails_cleanly() -> None:
    async with _ActorType() as my_actor:
        assert my_actor._is_initialized
        await my_actor.fail()
    assert my_actor._is_initialized is False


async def test_actor_handles_failure_gracefully() -> None:
    my_actor = None

    with contextlib.suppress(Exception):
        async with _ActorType() as my_actor:
            assert my_actor._is_initialized
            raise Exception('Failed')  # noqa: TRY002

    assert my_actor is not None
    assert my_actor._is_initialized is False


async def test_fail_without_init_raises_error() -> None:
    with pytest.raises(RuntimeError):
        await Actor.fail()


async def test_actor_reboot_fails_locally() -> None:
    with pytest.raises(RuntimeError):
        await Actor.reboot()


@pytest.mark.skipif(sys.version_info >= (3, 13), reason='Suffers flaky behavior on Python 3.13')
async def test_actor_handles_migrating_event_correctly(monkeypatch: pytest.MonkeyPatch) -> None:
    # This should test whether when you get a MIGRATING event,
    # the Actor automatically emits the PERSIST_STATE event with data `{'isMigrating': True}`
    monkeypatch.setenv(ApifyEnvVars.PERSIST_STATE_INTERVAL_MILLIS, '500')
    monkeypatch.setenv(ApifyEnvVars.IS_AT_HOME, '1')
    monkeypatch.setenv(ActorEnvVars.RUN_ID, 'asdf')

    persist_state_events_data = []

    def log_persist_state(data: Any) -> None:
        nonlocal persist_state_events_data
        persist_state_events_data.append(data)

    async def handler(websocket: websockets.asyncio.server.ServerConnection) -> None:
        await websocket.wait_closed()

    async with websockets.asyncio.server.serve(handler, host='localhost') as ws_server:
        port: int = ws_server.sockets[0].getsockname()[1]  # type: ignore[index]
        monkeypatch.setenv(ApifyEnvVars.ACTOR_EVENTS_WS_URL, f'ws://localhost:{port}')

        mock_run_client = Mock()
        mock_run_client.run.return_value.get = AsyncMock(
            side_effect=lambda: {
                'id': 'asdf',
                'actId': 'asdf',
                'userId': 'adsf',
                'startedAt': datetime.now(timezone.utc),
                'status': 'RUNNING',
                'meta': {'origin': 'DEVELOPMENT'},
                'stats': {
                    'inputBodyLen': 99,
                    'restartCount': 0,
                    'resurrectCount': 0,
                    'computeUnits': 1,
                },
                'options': {
                    'build': 'asdf',
                    'timeoutSecs': 4,
                    'memoryMbytes': 1024,
                    'diskMbytes': 1024,
                },
                'buildId': 'hjkl',
                'defaultDatasetId': 'hjkl',
                'defaultKeyValueStoreId': 'hjkl',
                'defaultRequestQueueId': 'hjkl',
                'containerUrl': 'https://hjkl',
            }
        )

        monkeypatch.setattr(Actor._charging_manager, '_client', mock_run_client)

        async with Actor:
            Actor.on(Event.PERSIST_STATE, log_persist_state)
            await asyncio.sleep(2)

            for socket in ws_server.connections:
                await socket.send(
                    json.dumps(
                        {
                            'name': 'migrating',
                            'data': {
                                'isMigrating': True,
                            },
                        }
                    )
                )

            await asyncio.sleep(1)

    assert len(persist_state_events_data) >= 3

    print(persist_state_events_data)

    # Check if the last event is from the migration
    assert persist_state_events_data.pop() == EventPersistStateData(is_migrating=True)

    # Check if all the other events are regular persist state events
    for event_data in persist_state_events_data:
        assert event_data == EventPersistStateData(is_migrating=False)
