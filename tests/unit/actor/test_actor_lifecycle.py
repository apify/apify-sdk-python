from typing import Any

import pytest

from apify import Actor
from apify.consts import ActorEventType


class TestActorInit:

    async def test_async_with_actor_properly_initialize(self) -> None:
        async with Actor:
            assert Actor._get_default_instance()._is_initialized
            # TODO: More checks
        assert not Actor._get_default_instance()._is_initialized

    async def test_actor_init(self) -> None:
        my_actor = Actor()
        await my_actor.init()
        assert my_actor._is_initialized is True
        await my_actor.exit()
        assert not my_actor._is_initialized

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

    async def test_with_actor_exit(self) -> None:
        is_persist_event_emitted = False
        is_migration = True

        def on_persist(data: Any) -> None:
            nonlocal is_migration
            nonlocal is_persist_event_emitted
            is_migration = data['isMigrating']
            is_persist_event_emitted = True
        my_actior = Actor()
        async with my_actior:
            assert my_actior._is_initialized
            my_actior.on(ActorEventType.PERSIST_STATE, on_persist)
            await my_actior.exit()
        # NOTE: Actor didn't call sys.exit() during testing.
        assert is_persist_event_emitted
        assert not is_migration
        assert not my_actior._is_initialized

    async def test_raise_on_exit_witout_init(self) -> None:
        with pytest.raises(RuntimeError):
            await Actor.exit()


class TestActorFail:

    async def test_with_actor_fail(self) -> None:
        my_actr = Actor()
        async with my_actr:
            assert my_actr._is_initialized
            await my_actr.fail()
        assert not my_actr._is_initialized

    async def test_with_actor_failed(self) -> None:
        my_actor = Actor()
        try:
            async with my_actor:
                assert my_actor._is_initialized
                raise Exception('Failed')
        except Exception:
            pass
        assert not my_actor._is_initialized

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
        assert not my_actor._is_initialized
        assert main_was_called
