import asyncio
from typing import Callable
from unittest.mock import AsyncMock

import pytest

from apify import Actor
from apify.consts import ActorEventType, ApifyEnvVars
from apify_client import ApifyClientAsync
from apify_client.consts import WebhookEventType

from ..conftest import ApifyClientAsyncPatcher


class TestActorInit:

    async def test_async_with_actor_properly_initialize(self) -> None:
        async with Actor:
            assert Actor._get_default_instance()._is_initialized
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
        async with Actor() as my_actor:
            assert my_actor._is_initialized
            await my_actor.fail()
        assert my_actor._is_initialized is False

    async def test_with_actor_failed(self) -> None:
        try:
            async with Actor() as my_actor:
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

    class TestActorNewClient:

        async def test_actor_new_client_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
            token = 'my-token'
            monkeypatch.setenv(ApifyEnvVars.TOKEN, token)
            my_actor = Actor()
            await my_actor.init()
            client = my_actor.new_client()
            assert type(client) == ApifyClientAsync
            assert client.token == token
            passed_token = 'my-passed-token'
            client_with_token = my_actor.new_client(token=passed_token)
            assert type(client_with_token) == ApifyClientAsync
            assert client_with_token.token == passed_token
            await my_actor.exit()


class TestActorCallStartAbortActor:

    async def test_actor_call(self, apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
        apify_client_async_patcher.patch('actor', 'call', return_value=None)
        actor_id = 'some-actor-id'
        my_actor = Actor()
        await my_actor.init()
        await my_actor.call(actor_id)
        assert len(apify_client_async_patcher.calls['actor']['call']) == 1
        # The first argument is ActorClientAsync, which was called, let's check its id.
        assert apify_client_async_patcher.calls['actor']['call'][0][0][0].resource_id == actor_id
        await my_actor.exit()

    async def test_actor_call_task(self, apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
        apify_client_async_patcher.patch('task', 'call', return_value=None)
        task_id = 'some-tasl-id'
        my_actor = Actor()
        await my_actor.init()
        await my_actor.call_task(task_id)
        assert len(apify_client_async_patcher.calls['task']['call']) == 1
        assert apify_client_async_patcher.calls['task']['call'][0][0][0].resource_id == task_id
        await my_actor.exit()

    async def test_actor_start(self, apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
        apify_client_async_patcher.patch('actor', 'start', return_value=None)
        actor_id = 'some-id'
        my_actor = Actor()
        await my_actor.init()
        await my_actor.start(actor_id)
        assert len(apify_client_async_patcher.calls['actor']['start']) == 1
        assert apify_client_async_patcher.calls['actor']['start'][0][0][0].resource_id == actor_id
        await my_actor.exit()

    async def test_actor_abort(self, apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
        apify_client_async_patcher.patch('run', 'abort', return_value=None)
        run_id = 'some-run-id'
        my_actor = Actor()
        await my_actor.init()
        await my_actor.abort(run_id)
        assert len(apify_client_async_patcher.calls['run']['abort']) == 1
        assert apify_client_async_patcher.calls['run']['abort'][0][0][0].resource_id == run_id
        await my_actor.exit()


class TestActorMethodsWorksOnlyOnPlatform:
    # NOTE: These medhods will be tested properly using integrations tests.

    async def test_actor_metamorpth_not_work_locally(self, capfd: pytest.CaptureFixture) -> None:
        async with Actor() as my_actor:
            await my_actor.metamorph('random-id')
        out, err = capfd.readouterr()
        assert 'Actor.metamorph() is only supported when running on the Apify platform.' in out

    async def test_actor_reboot_not_work_locally(self, capfd: pytest.CaptureFixture) -> None:
        async with Actor() as my_actor:
            await my_actor.reboot()
        out, err = capfd.readouterr()
        assert 'Actor.reboot() is only supported when running on the Apify platform.' in out

    async def test_actor_add_webhook_not_work_locally(self, capfd: pytest.CaptureFixture) -> None:
        async with Actor() as my_actor:
            await my_actor.add_webhook(event_types=[WebhookEventType.ACTOR_BUILD_ABORTED], request_url='https://example.com')
        out, err = capfd.readouterr()
        assert 'Actor.add_webhook() is only supported when running on the Apify platform.' in out

    async def test_actor_set_status_message_not_work_locally(self, capfd: pytest.CaptureFixture) -> None:
        async with Actor() as my_actor:
            await my_actor.set_status_message('test')
        out, err = capfd.readouterr()
        assert 'Actor.set_status_message() is only supported when running on the Apify platform.' in out
