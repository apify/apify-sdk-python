import pytest

from apify import Actor
from apify_client import ApifyClientAsync
from apify_shared.consts import ApifyEnvVars, WebhookEventType

from ..conftest import ApifyClientAsyncPatcher


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
        task_id = 'some-task-id'
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

    async def test_actor_metamorpth_not_work_locally(self, caplog: pytest.LogCaptureFixture) -> None:
        async with Actor() as my_actor:
            await my_actor.metamorph('random-id')
        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == 'ERROR'
        assert 'Actor.metamorph() is only supported when running on the Apify platform.' in caplog.records[0].message

    async def test_actor_reboot_not_work_locally(self, caplog: pytest.LogCaptureFixture) -> None:
        async with Actor() as my_actor:
            await my_actor.reboot()
        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == 'ERROR'
        assert 'Actor.reboot() is only supported when running on the Apify platform.' in caplog.records[0].message

    async def test_actor_add_webhook_not_work_locally(self, caplog: pytest.LogCaptureFixture) -> None:
        async with Actor() as my_actor:
            await my_actor.add_webhook(event_types=[WebhookEventType.ACTOR_BUILD_ABORTED], request_url='https://example.com')
        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == 'ERROR'
        assert 'Actor.add_webhook() is only supported when running on the Apify platform.' in caplog.records[0].message

    async def test_actor_set_status_message_mock_locally(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level('INFO')
        async with Actor() as my_actor:
            await my_actor.set_status_message('test-status-message')
        matching_records = [record for record in caplog.records if 'test-status-message' in record.message]
        assert len(matching_records) == 1
        assert matching_records[0].levelname == 'INFO'
        assert '[Status message]: test-status-message' in matching_records[0].message

    async def test_actor_set_status_message_terminal_mock_locally(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level('INFO')
        async with Actor() as my_actor:
            await my_actor.fail(status_message='test-terminal-message')
        matching_records = [record for record in caplog.records if 'test-terminal-message' in record.message]
        assert len(matching_records) == 1
        assert matching_records[0].levelname == 'INFO'
        assert '[Terminal status message]: test-terminal-message' in matching_records[0].message
