from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from apify_client import ApifyClientAsync
from apify_shared.consts import ApifyEnvVars, WebhookEventType

from apify import Actor, Webhook
from apify._actor import _ActorType

if TYPE_CHECKING:
    import pytest

    from ..conftest import ApifyClientAsyncPatcher


class TestActorNewClient:
    async def test_actor_new_client_config(self: TestActorNewClient, monkeypatch: pytest.MonkeyPatch) -> None:
        token = 'my-token'
        monkeypatch.setenv(ApifyEnvVars.TOKEN, token)
        my_actor = _ActorType()
        await my_actor.init()

        client = my_actor.new_client()
        assert isinstance(client, ApifyClientAsync)
        assert client.token == token

        passed_token = 'my-passed-token'
        client_with_token = my_actor.new_client(token=passed_token)
        assert isinstance(client_with_token, ApifyClientAsync)
        assert client_with_token.token == passed_token

        await my_actor.exit()


class TestActorCallStartAbortActor:
    FAKE_ACTOR_RUN: ClassVar = {
        'id': 'asdfasdf',
        'buildId': '3ads35',
        'buildNumber': '3.4.5',
        'actId': 'actor_id',
        'actorId': 'actor_id',
        'userId': 'user_id',
        'startedAt': '2024-08-08 12:12:44',
        'status': 'RUNNING',
        'meta': {'origin': 'API'},
        'containerUrl': 'http://0.0.0.0:3333',
        'defaultDatasetId': 'dhasdrfughaerguoi',
        'defaultKeyValueStoreId': 'asjkldhguiofg',
        'defaultRequestQueueId': 'lkjgklserjghios',
        'stats': {
            'inputBodyLen': 0,
            'restartCount': 0,
            'resurrectCount': 0,
            'memAvgBytes': 0,
            'memMaxBytes': 0,
            'memCurrentBytes': 0,
            'cpuAvgUsage': 0,
            'cpuMaxUsage': 0,
            'cpuCurrentUsage': 0,
            'netRxBytes': 0,
            'netTxBytes': 0,
            'durationMillis': 3333,
            'runTimeSecs': 33,
            'metamorph': 0,
            'computeUnits': 4.33,
        },
        'options': {
            'build': '',
            'timeoutSecs': 44,
            'memoryMbytes': 4096,
            'diskMbytes': 16384,
        },
    }

    async def test_actor_call(
        self: TestActorCallStartAbortActor,
        apify_client_async_patcher: ApifyClientAsyncPatcher,
    ) -> None:
        apify_client_async_patcher.patch('actor', 'call', return_value=self.FAKE_ACTOR_RUN)
        actor_id = 'some-actor-id'

        async with Actor:
            await Actor.call(actor_id)

        assert len(apify_client_async_patcher.calls['actor']['call']) == 1
        # The first argument is ActorClientAsync, which was called, let's check its id.
        assert apify_client_async_patcher.calls['actor']['call'][0][0][0].resource_id == actor_id

    async def test_actor_call_task(
        self: TestActorCallStartAbortActor,
        apify_client_async_patcher: ApifyClientAsyncPatcher,
    ) -> None:
        apify_client_async_patcher.patch('task', 'call', return_value=self.FAKE_ACTOR_RUN)
        task_id = 'some-task-id'

        async with Actor:
            await Actor.call_task(task_id)

        assert len(apify_client_async_patcher.calls['task']['call']) == 1
        assert apify_client_async_patcher.calls['task']['call'][0][0][0].resource_id == task_id

    async def test_actor_start(
        self: TestActorCallStartAbortActor,
        apify_client_async_patcher: ApifyClientAsyncPatcher,
    ) -> None:
        apify_client_async_patcher.patch('actor', 'start', return_value=self.FAKE_ACTOR_RUN)
        actor_id = 'some-id'

        async with Actor:
            await Actor.start(actor_id)

        assert len(apify_client_async_patcher.calls['actor']['start']) == 1
        assert apify_client_async_patcher.calls['actor']['start'][0][0][0].resource_id == actor_id

    async def test_actor_abort(
        self: TestActorCallStartAbortActor,
        apify_client_async_patcher: ApifyClientAsyncPatcher,
    ) -> None:
        apify_client_async_patcher.patch('run', 'abort', return_value=self.FAKE_ACTOR_RUN)
        run_id = 'some-run-id'

        async with Actor:
            await Actor.abort(run_id)

        assert len(apify_client_async_patcher.calls['run']['abort']) == 1
        assert apify_client_async_patcher.calls['run']['abort'][0][0][0].resource_id == run_id


class TestActorMethodsWorksOnlyOnPlatform:
    # NOTE: These methods will be tested properly using integrations tests.

    async def test_actor_metamorpth_not_work_locally(
        self: TestActorMethodsWorksOnlyOnPlatform,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        async with Actor:
            await Actor.metamorph('random-id')

        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == 'ERROR'
        assert 'Actor.metamorph() is only supported when running on the Apify platform.' in caplog.records[0].message

    async def test_actor_reboot_not_work_locally(
        self: TestActorMethodsWorksOnlyOnPlatform,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        async with Actor:
            await Actor.reboot()

        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == 'ERROR'
        assert 'Actor.reboot() is only supported when running on the Apify platform.' in caplog.records[0].message

    async def test_actor_add_webhook_not_work_locally(
        self: TestActorMethodsWorksOnlyOnPlatform,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        async with Actor:
            await Actor.add_webhook(
                Webhook(event_types=[WebhookEventType.ACTOR_BUILD_ABORTED], request_url='https://example.com')
            )

        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == 'ERROR'
        assert 'Actor.add_webhook() is only supported when running on the Apify platform.' in caplog.records[0].message

    async def test_actor_set_status_message_mock_locally(
        self: TestActorMethodsWorksOnlyOnPlatform,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.set_level('INFO')
        async with Actor:
            await Actor.set_status_message('test-status-message')

        matching_records = [record for record in caplog.records if 'test-status-message' in record.message]
        assert len(matching_records) == 1
        assert matching_records[0].levelname == 'INFO'
        assert '[Status message]: test-status-message' in matching_records[0].message

    async def test_actor_set_status_message_terminal_mock_locally(
        self: TestActorMethodsWorksOnlyOnPlatform,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.set_level('INFO')
        async with Actor:
            await Actor.fail(status_message='test-terminal-message')

        matching_records = [record for record in caplog.records if 'test-terminal-message' in record.message]
        assert len(matching_records) == 1
        assert matching_records[0].levelname == 'INFO'
        assert '[Terminal status message]: test-terminal-message' in matching_records[0].message
