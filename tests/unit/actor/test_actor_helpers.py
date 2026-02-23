from __future__ import annotations

import asyncio
import warnings
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest

from apify_client import ApifyClientAsync
from apify_client._models import Run, WebhookEventType
from apify_shared.consts import ApifyEnvVars
from crawlee.events._types import Event

from apify import Actor, Webhook
from apify._actor import _ActorType

if TYPE_CHECKING:
    from ..conftest import ApifyClientAsyncPatcher


@pytest.fixture
def fake_actor_run() -> Run:
    return Run.model_validate(
        {
            'id': 'asdfasdf',
            'buildId': '3ads35',
            'buildNumber': '3.4.5',
            'actId': 'actor_id',
            'actorId': 'actor_id',
            'userId': 'user_id',
            'startedAt': '2024-08-08T12:12:44Z',
            'status': 'RUNNING',
            'meta': {'origin': 'API'},
            'containerUrl': 'http://0.0.0.0:3333',
            'defaultDatasetId': 'dhasdrfughaerguoi',
            'defaultKeyValueStoreId': 'asjkldhguiofg',
            'defaultRequestQueueId': 'lkjgklserjghios',
            'generalAccess': 'RESTRICTED',
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
    )


async def test_new_client_config_creation(monkeypatch: pytest.MonkeyPatch) -> None:
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


async def test_call_actor(apify_client_async_patcher: ApifyClientAsyncPatcher, fake_actor_run: Run) -> None:
    apify_client_async_patcher.patch('actor', 'call', return_value=fake_actor_run)
    actor_id = 'some-actor-id'

    async with Actor:
        await Actor.call(actor_id)

    assert len(apify_client_async_patcher.calls['actor']['call']) == 1
    # The first argument is ActorClientAsync, which was called, let's check its id.
    assert apify_client_async_patcher.calls['actor']['call'][0][0][0].resource_id == actor_id


async def test_call_actor_task(apify_client_async_patcher: ApifyClientAsyncPatcher, fake_actor_run: Run) -> None:
    apify_client_async_patcher.patch('task', 'call', return_value=fake_actor_run)
    task_id = 'some-task-id'

    async with Actor:
        await Actor.call_task(task_id)

    assert len(apify_client_async_patcher.calls['task']['call']) == 1
    assert apify_client_async_patcher.calls['task']['call'][0][0][0].resource_id == task_id


async def test_start_actor(apify_client_async_patcher: ApifyClientAsyncPatcher, fake_actor_run: Run) -> None:
    apify_client_async_patcher.patch('actor', 'start', return_value=fake_actor_run)
    actor_id = 'some-id'

    async with Actor:
        await Actor.start(actor_id)

    assert len(apify_client_async_patcher.calls['actor']['start']) == 1
    assert apify_client_async_patcher.calls['actor']['start'][0][0][0].resource_id == actor_id


async def test_abort_actor_run(apify_client_async_patcher: ApifyClientAsyncPatcher, fake_actor_run: Run) -> None:
    apify_client_async_patcher.patch('run', 'abort', return_value=fake_actor_run)
    run_id = 'some-run-id'

    async with Actor:
        await Actor.abort(run_id)

    assert len(apify_client_async_patcher.calls['run']['abort']) == 1
    assert apify_client_async_patcher.calls['run']['abort'][0][0][0].resource_id == run_id


# NOTE: The following methods are properly tested using integrations tests.


async def test_metamorph_fails_locally(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level('WARNING')
    async with Actor:
        await Actor.metamorph('random-id')

    matching = [r for r in caplog.records if 'Actor.metamorph()' in r.message]
    assert len(matching) == 1
    assert matching[0].levelname == 'ERROR'
    assert 'only supported when running on the Apify platform' in matching[0].message


async def test_reboot_fails_locally(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level('WARNING')
    async with Actor:
        await Actor.reboot()

    matching = [r for r in caplog.records if 'Actor.reboot()' in r.message]
    assert len(matching) == 1
    assert matching[0].levelname == 'ERROR'
    assert 'only supported when running on the Apify platform' in matching[0].message


async def test_add_webhook_fails_locally(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level('WARNING')
    async with Actor:
        await Actor.add_webhook(
            Webhook(event_types=[WebhookEventType.ACTOR_BUILD_ABORTED.value], request_url='https://example.com')
        )

    matching = [r for r in caplog.records if 'Actor.add_webhook()' in r.message]
    assert len(matching) == 1
    assert matching[0].levelname == 'ERROR'
    assert 'only supported when running on the Apify platform' in matching[0].message


async def test_set_status_message_locally(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level('INFO')
    async with Actor:
        await Actor.set_status_message('test-status-message')

    matching_records = [record for record in caplog.records if 'test-status-message' in record.message]
    assert len(matching_records) == 1
    assert matching_records[0].levelname == 'INFO'
    assert '[Status message]: test-status-message' in matching_records[0].message


async def test_set_terminal_status_message_locally(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level('INFO')
    async with Actor:
        await Actor.fail(status_message='test-terminal-message')

    matching_records = [record for record in caplog.records if 'test-terminal-message' in record.message]
    assert len(matching_records) == 1
    assert matching_records[0].levelname == 'INFO'
    assert '[Terminal status message]: test-terminal-message' in matching_records[0].message


async def test_push_data_with_empty_data() -> None:
    """Test that push_data returns None when data is empty."""
    async with Actor:
        result = await Actor.push_data([])
        assert result is None

        result = await Actor.push_data({})
        assert result is None


async def test_off_removes_event_listener(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that Actor.off() removes an event listener."""
    monkeypatch.setenv(ApifyEnvVars.PERSIST_STATE_INTERVAL_MILLIS, '50')
    called = False

    async def listener(_data: object) -> None:
        nonlocal called
        called = True

    async with Actor:
        Actor.on(Event.PERSIST_STATE, listener)
        Actor.off(Event.PERSIST_STATE, listener)
        # Wait long enough for at least one PERSIST_STATE event to fire
        await asyncio.sleep(0.2)
        # Verify the listener was NOT called because it was removed
        assert called is False


_ACTOR_REMOTE_METHODS = [
    pytest.param('actor', 'start', 'start', 'some-actor-id', id='start'),
    pytest.param('actor', 'call', 'call', 'some-actor-id', id='call'),
    pytest.param('task', 'call', 'call_task', 'some-task-id', id='call_task'),
]


@pytest.mark.parametrize(('client_resource', 'client_method', 'actor_method_name', 'entity_id'), _ACTOR_REMOTE_METHODS)
async def test_remote_method_with_webhooks(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
    fake_actor_run: dict,
    client_resource: str,
    client_method: str,
    actor_method_name: str,
    entity_id: str,
) -> None:
    """Test that start/call/call_task correctly serialize webhooks."""
    apify_client_async_patcher.patch(client_resource, client_method, return_value=fake_actor_run)

    async with Actor:
        actor_method = getattr(Actor, actor_method_name)
        await actor_method(
            entity_id,
            webhooks=[Webhook(event_types=[WebhookEventType.ACTOR_RUN_SUCCEEDED], request_url='https://example.com')],
        )

    calls = apify_client_async_patcher.calls[client_resource][client_method]
    assert len(calls) == 1
    _, kwargs = calls[0][0], calls[0][1]
    assert 'webhooks' in kwargs
    assert kwargs['webhooks'] is not None


@pytest.mark.parametrize(('client_resource', 'client_method', 'actor_method_name', 'entity_id'), _ACTOR_REMOTE_METHODS)
async def test_remote_method_with_timedelta_timeout(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
    fake_actor_run: dict,
    client_resource: str,
    client_method: str,
    actor_method_name: str,
    entity_id: str,
) -> None:
    """Test that start/call/call_task accept a timedelta timeout."""
    apify_client_async_patcher.patch(client_resource, client_method, return_value=fake_actor_run)

    async with Actor:
        actor_method = getattr(Actor, actor_method_name)
        await actor_method(entity_id, timeout=timedelta(seconds=120))

    calls = apify_client_async_patcher.calls[client_resource][client_method]
    assert len(calls) == 1
    _, kwargs = calls[0][0], calls[0][1]
    assert kwargs.get('timeout') == timedelta(seconds=120)


async def test_call_actor_with_remaining_time_deprecation(
    apify_client_async_patcher: ApifyClientAsyncPatcher, fake_actor_run: dict
) -> None:
    """Test that call() with RemainingTime emits deprecation warning."""
    apify_client_async_patcher.patch('actor', 'call', return_value=fake_actor_run)

    async with Actor:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')
            await Actor.call('some-actor-id', timeout='RemainingTime')
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) == 1
            assert 'RemainingTime' in str(deprecation_warnings[0].message)


@pytest.mark.parametrize(('client_resource', 'client_method', 'actor_method_name', 'entity_id'), _ACTOR_REMOTE_METHODS)
async def test_remote_method_with_invalid_timeout(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
    fake_actor_run: dict,
    client_resource: str,
    client_method: str,
    actor_method_name: str,
    entity_id: str,
) -> None:
    """Test that start/call/call_task raise ValueError for invalid timeout."""
    apify_client_async_patcher.patch(client_resource, client_method, return_value=fake_actor_run)

    async with Actor:
        actor_method = getattr(Actor, actor_method_name)
        with pytest.raises(ValueError, match='Invalid timeout'):
            await actor_method(entity_id, timeout='invalid')


async def test_abort_with_status_message(
    apify_client_async_patcher: ApifyClientAsyncPatcher, fake_actor_run: dict
) -> None:
    """Test that abort() updates status message before aborting."""
    apify_client_async_patcher.patch('run', 'update', return_value=fake_actor_run)
    apify_client_async_patcher.patch('run', 'abort', return_value=fake_actor_run)

    async with Actor:
        await Actor.abort('run-id', status_message='Aborting due to error')

    assert len(apify_client_async_patcher.calls['run']['update']) == 1
    assert len(apify_client_async_patcher.calls['run']['abort']) == 1


async def test_get_remaining_time_warns_when_not_at_home(caplog: pytest.LogCaptureFixture) -> None:
    """Test that _get_remaining_time logs warning when not at home."""
    caplog.set_level('WARNING')
    async with Actor:
        # Actor is not at home, so _get_remaining_time should return None and log warning
        result = Actor._get_remaining_time()
        assert result is None
    assert any('inherit' in msg or 'RemainingTime' in msg for msg in caplog.messages)
