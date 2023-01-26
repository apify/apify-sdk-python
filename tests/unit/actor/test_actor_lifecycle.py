import asyncio
from typing import Callable
from unittest.mock import AsyncMock

import pytest

from apify import Actor
from apify.consts import ActorEventType, ApifyEnvVars


class TestActorInit:

    async def test_async_with_actor_properly_initialize(self) -> None:
        async with Actor:
            assert Actor._get_default_instance()._is_initialized
            # TODO: More checks
        assert Actor._get_default_instance()._is_initialized is False

    async def test_actor_init(self) -> None:
        my_actor = Actor()
        await my_actor.init()
        assert my_actor._is_initialized is True
        await my_actor.exit()
        assert my_actor._is_initialized is False

    async def test_double_init(self) -> None:
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

    async def test_with_actor_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ApifyEnvVars.SYSTEM_INFO_INTERVAL_MILLIS, '100')
        monkeypatch.setenv(ApifyEnvVars.PERSIST_STATE_INTERVAL_MILLIS, '100')
        on_persist = list()
        on_system_info = list()

        def on_event(event_type: ActorEventType) -> Callable:
            nonlocal on_persist
            nonlocal on_system_info
            if event_type == ActorEventType.PERSIST_STATE:
                return lambda data: on_persist.append(data)
            elif event_type == ActorEventType.SYSTEM_INFO:
                return lambda data: on_system_info.append(data)
            return lambda data: print(data)

        my_actor = Actor()
        async with my_actor:
            assert my_actor._is_initialized
            my_actor.on(ActorEventType.PERSIST_STATE, on_event(ActorEventType.PERSIST_STATE))
            my_actor.on(ActorEventType.SYSTEM_INFO, on_event(ActorEventType.SYSTEM_INFO))
            await asyncio.sleep(1)

        on_persist_count = len(on_persist)
        on_system_info_count = len(on_system_info)
        assert on_persist_count != 0
        assert on_system_info_count != 0
        # Check if envents stopped emitting.
        await asyncio.sleep(0.2)
        assert on_persist_count == len(on_persist)
        assert on_system_info_count == len(on_system_info)

    async def test_raise_on_exit_witout_init(self) -> None:
        with pytest.raises(RuntimeError):
            await Actor.exit()


class TestActorFail:

    async def test_with_actor_fail(self) -> None:
        my_actr = Actor()
        async with my_actr:
            assert my_actr._is_initialized
            await my_actr.fail()
        assert my_actr._is_initialized is False

    async def test_with_actor_failed(self) -> None:
        my_actor = Actor()
        try:
            async with my_actor:
                assert my_actor._is_initialized
                raise Exception('Failed')
        except Exception:
            pass
        assert my_actor._is_initialized is False

    async def test_raise_on_fail_witout_init(self) -> None:
        with pytest.raises(RuntimeError):
            await Actor.fail()

    async def test_actor_reboot_not_work_locally(self) -> None:
        with pytest.raises(RuntimeError):
            await Actor.reboot()


class TestActorMainMethod:

    async def test_actor_main_method(self) -> None:
        my_actor = Actor()
        main_was_called = False

        async def actor_function() -> None:
            nonlocal main_was_called
            main_was_called = True
            assert my_actor._is_initialized
        await my_actor.main(actor_function)
        assert my_actor._is_initialized is False
        assert main_was_called

    async def test_actor_main_method_throw_exception(self) -> None:
        my_actor = Actor()
        err = Exception('Failed')
        my_actor.fail = AsyncMock()  # type: ignore

        async def actor_function() -> None:
            nonlocal err
            raise err

        await my_actor.main(actor_function)
        # NOTE: Actor didn't call sys.exit() during testing, check if fail was called.
        my_actor.fail.assert_called_with(exit_code=91, _exc_type=type(err), _exc_value=err, _exc_traceback=err.__traceback__)

    async def test_actor_main_method_raise_return_value(self) -> None:
        my_actor = Actor()
        expected_string = 'Hello world'

        async def actor_function() -> str:
            nonlocal expected_string
            return expected_string

        returned_value = await my_actor.main(actor_function)
        assert returned_value == expected_string
