from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime
from typing import Any, Callable
from unittest.mock import AsyncMock

import pytest
from apify_shared.consts import ActorEventTypes, ApifyEnvVars

from apify import Actor


class TestActorInit:
    async def test_async_with_actor_properly_initialize(self: TestActorInit) -> None:
        async with Actor:
            assert Actor._get_default_instance()._is_initialized
        assert Actor._get_default_instance()._is_initialized is False

    async def test_actor_init(self: TestActorInit) -> None:
        my_actor = Actor()

        await my_actor.init()
        assert my_actor._is_initialized is True

        await my_actor.exit()
        assert my_actor._is_initialized is False

    async def test_double_init(self: TestActorInit) -> None:
        my_actor = Actor()

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

        def on_event(event_type: ActorEventTypes) -> Callable:
            nonlocal on_persist
            nonlocal on_system_info
            if event_type == ActorEventTypes.PERSIST_STATE:
                return lambda data: on_persist.append(data)
            if event_type == ActorEventTypes.SYSTEM_INFO:
                return lambda data: on_system_info.append(data)
            return lambda data: print(data)

        my_actor = Actor()
        async with my_actor:
            assert my_actor._is_initialized
            my_actor.on(ActorEventTypes.PERSIST_STATE, on_event(ActorEventTypes.PERSIST_STATE))
            my_actor.on(ActorEventTypes.SYSTEM_INFO, on_event(ActorEventTypes.SYSTEM_INFO))
            await asyncio.sleep(1)

        on_persist_count = len(on_persist)
        on_system_info_count = len(on_system_info)
        assert on_persist_count != 0
        assert on_system_info_count != 0

        # Check if events stopped emitting.
        await asyncio.sleep(0.2)
        assert on_persist_count == len(on_persist)
        assert on_system_info_count == len(on_system_info)
        # Check `createdAt` is a datetime (so it's the same locally and on platform)
        assert isinstance(on_system_info[0]['createdAt'], datetime)

    async def test_raise_on_exit_witout_init(self: TestActorExit) -> None:
        with pytest.raises(RuntimeError):
            await Actor.exit()


class TestActorFail:
    async def test_with_actor_fail(self: TestActorFail) -> None:
        async with Actor() as my_actor:
            assert my_actor._is_initialized
            await my_actor.fail()
        assert my_actor._is_initialized is False

    async def test_with_actor_failed(self: TestActorFail) -> None:
        with contextlib.suppress(Exception):
            async with Actor() as my_actor:
                assert my_actor._is_initialized
                raise Exception('Failed')  # noqa: TRY002
        assert my_actor._is_initialized is False

    async def test_raise_on_fail_without_init(self: TestActorFail) -> None:
        with pytest.raises(RuntimeError):
            await Actor.fail()

    async def test_actor_reboot_not_work_locally(self: TestActorFail) -> None:
        with pytest.raises(RuntimeError):
            await Actor.reboot()


class TestActorMainMethod:
    async def test_actor_main_method(self: TestActorMainMethod) -> None:
        my_actor = Actor()
        main_was_called = False

        async def actor_function() -> None:
            nonlocal main_was_called
            main_was_called = True
            assert my_actor._is_initialized

        await my_actor.main(actor_function)
        assert my_actor._is_initialized is False
        assert main_was_called

    async def test_actor_main_method_throw_exception(self: TestActorMainMethod) -> None:
        my_actor = Actor()
        err = Exception('Failed')
        my_actor.fail = AsyncMock()  # type: ignore

        async def actor_function() -> None:
            nonlocal err
            raise err

        await my_actor.main(actor_function)
        # NOTE: Actor didn't call sys.exit() during testing, check if fail was called.
        my_actor.fail.assert_called_with(exit_code=91, exception=err)

        # This is necessary to stop the event emitting intervals
        await my_actor.exit()

    async def test_actor_main_method_raise_return_value(self: TestActorMainMethod) -> None:
        my_actor = Actor()
        expected_string = 'Hello world'

        async def actor_function() -> str:
            nonlocal expected_string
            return expected_string

        returned_value = await my_actor.main(actor_function)
        assert returned_value == expected_string


class TestMigratingEvent:
    async def test_migrating_event(self: TestMigratingEvent, monkeypatch: pytest.MonkeyPatch) -> None:
        # This should test whether when you get a MIGRATING event,
        # the actor automatically emits the PERSIST_STATE event with data `{'isMigrating': True}`
        monkeypatch.setenv(ApifyEnvVars.PERSIST_STATE_INTERVAL_MILLIS, '500')

        persist_state_events_data = []

        def log_persist_state(data: Any) -> None:
            nonlocal persist_state_events_data
            persist_state_events_data.append(data)

        async with Actor:
            Actor.on(ActorEventTypes.PERSIST_STATE, log_persist_state)
            await asyncio.sleep(2)
            Actor._get_default_instance()._event_manager.emit(ActorEventTypes.MIGRATING, None)
            await asyncio.sleep(1)

        assert len(persist_state_events_data) >= 3

        print(persist_state_events_data)

        # Check if the last event is from the migration
        assert persist_state_events_data.pop() == {'isMigrating': True}

        # Check if all the other events are regular persist state events
        for event_data in persist_state_events_data:
            assert event_data == {'isMigrating': False}
