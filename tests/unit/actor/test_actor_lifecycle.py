from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any, Callable

import pytest
import websockets.server

import apify.actor
from apify.actor import Actor, _ActorType
from apify_shared.consts import ApifyEnvVars
from crawlee.events._types import Event, EventPersistStateData


class TestActorInit:
    async def test_async_with_actor_properly_initialize(self: TestActorInit) -> None:
        async with Actor:
            assert apify.actor._default_instance is not None
            assert apify.actor._default_instance._is_initialized
        assert not apify.actor._default_instance._is_initialized

    async def test_actor_init(self: TestActorInit) -> None:
        my_actor = _ActorType()

        await my_actor.init()
        assert my_actor._is_initialized is True

        await my_actor.exit()
        assert my_actor._is_initialized is False

    async def test_double_init(self: TestActorInit) -> None:
        my_actor = _ActorType()

        await my_actor.init()
        with pytest.raises(RuntimeError):
            await my_actor.init()
        await my_actor.exit()

        await Actor.init()
        with pytest.raises(RuntimeError):
            await Actor.init()
        await Actor.exit()


class TestActorExit:
    async def test_with_actor_exit(self: TestActorExit, monkeypatch: pytest.MonkeyPatch) -> None:
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

    async def test_raise_on_exit_without_init(self: TestActorExit) -> None:
        with pytest.raises(RuntimeError):
            await Actor.exit()


class TestActorFail:
    async def test_with_actor_fail(self: TestActorFail) -> None:
        async with _ActorType() as my_actor:
            assert my_actor._is_initialized
            await my_actor.fail()
        assert my_actor._is_initialized is False

    async def test_with_actor_failed(self: TestActorFail) -> None:
        my_actor = None

        with contextlib.suppress(Exception):
            async with _ActorType() as my_actor:
                assert my_actor._is_initialized
                raise Exception('Failed')  # noqa: TRY002

        assert my_actor is not None
        assert my_actor._is_initialized is False

    async def test_raise_on_fail_without_init(self: TestActorFail) -> None:
        with pytest.raises(RuntimeError):
            await Actor.fail()

    async def test_actor_reboot_not_work_locally(self: TestActorFail) -> None:
        with pytest.raises(RuntimeError):
            await Actor.reboot()


class TestMigratingEvent:
    async def test_migrating_event(self: TestMigratingEvent, monkeypatch: pytest.MonkeyPatch) -> None:
        # This should test whether when you get a MIGRATING event,
        # the Actor automatically emits the PERSIST_STATE event with data `{'isMigrating': True}`
        monkeypatch.setenv(ApifyEnvVars.PERSIST_STATE_INTERVAL_MILLIS, '500')
        monkeypatch.setenv(ApifyEnvVars.IS_AT_HOME, '1')

        persist_state_events_data = []

        def log_persist_state(data: Any) -> None:
            nonlocal persist_state_events_data
            persist_state_events_data.append(data)

        async def handler(websocket: websockets.server.WebSocketServerProtocol) -> None:
            await websocket.wait_closed()

        async with websockets.server.serve(handler, host='localhost') as ws_server:
            port: int = ws_server.sockets[0].getsockname()[1]  # type: ignore[index]
            monkeypatch.setenv(ApifyEnvVars.ACTOR_EVENTS_WS_URL, f'ws://localhost:{port}')

            async with Actor:
                Actor.on(Event.PERSIST_STATE, log_persist_state)
                await asyncio.sleep(2)

                for socket in ws_server.websockets:
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
