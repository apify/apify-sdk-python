from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, Mock

import pytest

from apify_client._models import Run

from apify import Actor
from apify._actor import _ActorType
from apify._child_runs import CHILD_RUNS_KEY

if TYPE_CHECKING:
    from ..conftest import ApifyClientAsyncPatcher
    from apify.storages import KeyValueStore


def make_run(run_id: str, status: str) -> Run:
    return Run.model_validate(
        {
            'id': run_id,
            'actId': 'actor_id',
            'userId': 'user_id',
            'startedAt': '2024-08-08T12:12:44Z',
            'status': status,
            'meta': {'origin': 'API'},
            'buildId': 'build_id',
            'defaultDatasetId': 'dataset_id',
            'defaultKeyValueStoreId': 'kvs_id',
            'defaultRequestQueueId': 'rq_id',
            'generalAccess': 'RESTRICTED',
            'stats': {'restartCount': 0, 'resurrectCount': 0, 'computeUnits': 0},
            'options': {'build': '', 'timeoutSecs': 44, 'memoryMbytes': 4096, 'diskMbytes': 16384},
        }
    )


async def record_child_run(
    name: str, run_id: str, *, actor_id: str | None = 'some-actor', task_id: str | None = None
) -> None:
    """Seed the registry the way an earlier attempt of this Actor run would have left it."""
    kvs = await Actor.open_key_value_store()
    await kvs.set_value(
        CHILD_RUNS_KEY, {name: {'actorId': actor_id, 'taskId': task_id, 'runId': run_id, 'previousRunIds': []}}
    )


async def test_named_start_records_run_in_kvs(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A named start persists the name -> run ID entry to the default KVS as soon as the run starts."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor:
        run = await Actor.start('some-actor', run_name='scrape-eu')
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert run.id == 'new-run'
    assert stored == {'scrape-eu': {'actorId': 'some-actor', 'taskId': None, 'runId': 'new-run', 'previousRunIds': []}}


async def test_unnamed_start_is_not_recorded(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A start without a name leaves the registry untouched."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor:
        await Actor.start('some-actor')
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert stored is None


@pytest.mark.parametrize(
    'status',
    [
        pytest.param('READY', id='ready'),
        pytest.param('RUNNING', id='running'),
        pytest.param('SUCCEEDED', id='succeeded'),
    ],
)
async def test_named_start_reuses_recorded_run(
    apify_client_async_patcher: ApifyClientAsyncPatcher, status: str
) -> None:
    """A recorded run that is active or succeeded is returned without starting a new one."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', status))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run')
        run = await Actor.start('some-actor', run_name='scrape-eu')

    assert run.id == 'old-run'
    assert run.status == status
    assert apify_client_async_patcher.calls['actor']['start'] == []


@pytest.mark.parametrize(
    'status',
    [
        pytest.param('ABORTED', id='aborted'),
        pytest.param('TIMED-OUT', id='timed out'),
    ],
)
async def test_named_start_resurrects_recorded_run(
    apify_client_async_patcher: ApifyClientAsyncPatcher, status: str
) -> None:
    """A recorded run that was aborted or timed out is resurrected, and its options are passed through."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', status))
    apify_client_async_patcher.patch('run', 'resurrect', return_value=make_run('old-run', 'RUNNING'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run')
        run = await Actor.start('some-actor', run_name='scrape-eu', memory_mbytes=2048)

    assert run.id == 'old-run'
    assert run.status == 'RUNNING'
    assert apify_client_async_patcher.calls['actor']['start'] == []
    [(args, kwargs)] = apify_client_async_patcher.calls['run']['resurrect']
    assert args[0].resource_id == 'old-run'
    assert kwargs['memory_mbytes'] == 2048


@pytest.mark.parametrize(
    'status',
    [
        pytest.param('ABORTING', id='aborting'),
        pytest.param('TIMING-OUT', id='timing out'),
    ],
)
async def test_named_start_resurrects_settling_run_after_it_finishes(
    apify_client_async_patcher: ApifyClientAsyncPatcher, status: str
) -> None:
    """A recorded run still aborting or timing out is waited for, then resurrected."""
    finished_status = {'ABORTING': 'ABORTED', 'TIMING-OUT': 'TIMED-OUT'}[status]
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', status))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=make_run('old-run', finished_status))
    apify_client_async_patcher.patch('run', 'resurrect', return_value=make_run('old-run', 'RUNNING'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run')
        run = await Actor.start('some-actor', run_name='scrape-eu')

    assert run.status == 'RUNNING'
    assert len(apify_client_async_patcher.calls['run']['wait_for_finish']) == 1
    assert len(apify_client_async_patcher.calls['run']['resurrect']) == 1


@pytest.mark.parametrize(
    'recorded_run',
    [
        pytest.param(make_run('old-run', 'FAILED'), id='failed'),
        pytest.param(None, id='not found'),
    ],
)
async def test_named_start_replaces_failed_or_missing_run(
    apify_client_async_patcher: ApifyClientAsyncPatcher, recorded_run: Run | None
) -> None:
    """A recorded run that failed or no longer exists is replaced by a new run and kept in the history."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=recorded_run)

    async with Actor:
        await record_child_run('scrape-eu', 'old-run')
        run = await Actor.start('some-actor', run_name='scrape-eu')
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert run.id == 'new-run'
    assert stored == {
        'scrape-eu': {'actorId': 'some-actor', 'taskId': None, 'runId': 'new-run', 'previousRunIds': ['old-run']}
    }


async def test_named_start_rejects_name_recorded_for_another_actor(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """Reusing a name for a different Actor raises instead of attaching to the other Actor's run."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run', actor_id='other-actor')
        with pytest.raises(ValueError, match='already recorded for Actor "other-actor"'):
            await Actor.start('some-actor', run_name='scrape-eu')

    assert apify_client_async_patcher.calls['actor']['start'] == []


async def test_named_start_rejects_name_recorded_for_task(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """Reusing a task run's name for an Actor raises instead of attaching to the task's run."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run', actor_id=None, task_id='some-task')
        with pytest.raises(ValueError, match='already recorded for task "some-task"'):
            await Actor.start('some-actor', run_name='scrape-eu')

    assert apify_client_async_patcher.calls['actor']['start'] == []


async def test_concurrent_named_starts_start_one_run(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """Concurrent starts under the same name start a single run and share it."""
    started = make_run('new-run', 'RUNNING')

    async def slow_start(*_args: Any, **_kwargs: Any) -> Run:
        await asyncio.sleep(0.05)
        return started

    apify_client_async_patcher.patch('actor', 'start', replacement_method=slow_start)
    apify_client_async_patcher.patch('run', 'get', return_value=started)

    async with Actor:
        runs = await asyncio.gather(*(Actor.start('some-actor', run_name='scrape-eu') for _ in range(3)))

    assert {run.id for run in runs} == {'new-run'}
    assert len(apify_client_async_patcher.calls['actor']['start']) == 1


async def test_concurrent_first_named_starts_share_one_registry(
    apify_client_async_patcher: ApifyClientAsyncPatcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Concurrent first named starts start a single run even when opening the default KVS yields to the event loop."""
    started = make_run('new-run', 'RUNNING')

    async def slow_start(*_args: Any, **_kwargs: Any) -> Run:
        await asyncio.sleep(0.05)
        return started

    apify_client_async_patcher.patch('actor', 'start', replacement_method=slow_start)
    apify_client_async_patcher.patch('run', 'get', return_value=started)
    open_key_value_store = _ActorType.open_key_value_store

    async def yielding_open_key_value_store(self: _ActorType, *args: Any, **kwargs: Any) -> KeyValueStore:
        # On the platform the default KVS is opened lazily through the API, so opening it suspends.
        await asyncio.sleep(0.01)
        return await open_key_value_store(self, *args, **kwargs)

    monkeypatch.setattr(_ActorType, 'open_key_value_store', yielding_open_key_value_store)

    # A fresh instance, since the registry binds the opener when the Actor is created.
    async with _ActorType() as actor:
        runs = await asyncio.gather(*(actor.start('some-actor', run_name='scrape-eu') for _ in range(3)))

    assert {run.id for run in runs} == {'new-run'}
    assert len(apify_client_async_patcher.calls['actor']['start']) == 1


async def test_named_call_waits_for_reattached_run(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A named call waits for the reattached run and streams only its new log lines."""
    streamed_log = MagicMock()
    get_streamed_log = Mock(return_value=streamed_log)
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', 'RUNNING'))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=make_run('old-run', 'SUCCEEDED'))
    apify_client_async_patcher.patch('run', 'get_status_message_watcher', return_value=MagicMock())
    apify_client_async_patcher.patch('run', 'get_streamed_log', replacement_method=get_streamed_log)

    async with Actor:
        await record_child_run('scrape-eu', 'old-run')
        run = await Actor.call('some-actor', run_name='scrape-eu')

    assert run.status == 'SUCCEEDED'
    assert get_streamed_log.call_args.kwargs['from_start'] is False
    streamed_log.__aenter__.assert_awaited_once()


async def test_named_call_streams_new_run_log_from_start(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A named call that starts a new run streams its log from the start."""
    get_streamed_log = Mock(return_value=MagicMock())
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=make_run('new-run', 'SUCCEEDED'))
    apify_client_async_patcher.patch('run', 'get_status_message_watcher', return_value=MagicMock())
    apify_client_async_patcher.patch('run', 'get_streamed_log', replacement_method=get_streamed_log)

    async with Actor:
        run = await Actor.call('some-actor', run_name='scrape-eu')

    assert run.id == 'new-run'
    assert run.status == 'SUCCEEDED'
    assert get_streamed_log.call_args.kwargs['from_start'] is True
    assert apify_client_async_patcher.calls['actor']['call'] == []


async def test_named_call_returns_succeeded_run_without_waiting(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """A named call whose recorded run already succeeded returns it without waiting or streaming logs."""
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', 'SUCCEEDED'))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=None)

    async with Actor:
        await record_child_run('scrape-eu', 'old-run')
        run = await Actor.call('some-actor', run_name='scrape-eu')

    assert run.id == 'old-run'
    assert apify_client_async_patcher.calls['run']['wait_for_finish'] == []


async def test_named_call_waits_for_resurrected_run(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A named call resurrects an aborted run with its own timeout and streams only the new log lines."""
    get_streamed_log = Mock(return_value=MagicMock())
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', 'ABORTED'))
    apify_client_async_patcher.patch('run', 'resurrect', return_value=make_run('old-run', 'RUNNING'))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=make_run('old-run', 'SUCCEEDED'))
    apify_client_async_patcher.patch('run', 'get_status_message_watcher', return_value=MagicMock())
    apify_client_async_patcher.patch('run', 'get_streamed_log', replacement_method=get_streamed_log)

    async with Actor:
        await record_child_run('scrape-eu', 'old-run')
        run = await Actor.call('some-actor', run_name='scrape-eu', timeout=timedelta(minutes=5))

    assert run.id == 'old-run'
    assert run.status == 'SUCCEEDED'
    assert apify_client_async_patcher.calls['actor']['start'] == []
    [(_, kwargs)] = apify_client_async_patcher.calls['run']['resurrect']
    assert kwargs['run_timeout'] == timedelta(minutes=5)
    assert get_streamed_log.call_args.kwargs['from_start'] is False


async def test_named_call_without_logger_only_waits(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A named call with `logger=None` waits for the run without redirecting its log or status messages."""
    get_streamed_log = Mock(return_value=MagicMock())
    get_status_message_watcher = Mock(return_value=MagicMock())
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=make_run('new-run', 'SUCCEEDED'))
    apify_client_async_patcher.patch('run', 'get_status_message_watcher', replacement_method=get_status_message_watcher)
    apify_client_async_patcher.patch('run', 'get_streamed_log', replacement_method=get_streamed_log)

    async with Actor:
        run = await Actor.call('some-actor', run_name='scrape-eu', logger=None)

    assert run.status == 'SUCCEEDED'
    assert len(apify_client_async_patcher.calls['run']['wait_for_finish']) == 1
    get_streamed_log.assert_not_called()
    get_status_message_watcher.assert_not_called()


async def test_named_start_rejects_malformed_registry(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A malformed registry in the default KVS raises a `ValueError` naming the key, without starting a run."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor:
        kvs = await Actor.open_key_value_store()
        await kvs.set_value(CHILD_RUNS_KEY, {'scrape-eu': {'runId': 'old-run'}})
        with pytest.raises(ValueError, match=CHILD_RUNS_KEY):
            await Actor.start('some-actor', run_name='scrape-eu')

    assert apify_client_async_patcher.calls['actor']['start'] == []


async def test_named_call_task_records_run_in_kvs(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A named task call starts the task, records the run under the task ID, and waits for it."""
    apify_client_async_patcher.patch('task', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=make_run('new-run', 'SUCCEEDED'))

    async with Actor:
        run = await Actor.call_task('some-task', run_name='scrape-eu')
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert run.status == 'SUCCEEDED'
    assert stored == {'scrape-eu': {'actorId': None, 'taskId': 'some-task', 'runId': 'new-run', 'previousRunIds': []}}
    assert apify_client_async_patcher.calls['task']['call'] == []


async def test_named_call_task_waits_for_reattached_run(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A named task call waits for the recorded running run without starting the task again."""
    apify_client_async_patcher.patch('task', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', 'RUNNING'))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=make_run('old-run', 'SUCCEEDED'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run', actor_id=None, task_id='some-task')
        run = await Actor.call_task('some-task', run_name='scrape-eu')

    assert run.id == 'old-run'
    assert run.status == 'SUCCEEDED'
    assert apify_client_async_patcher.calls['task']['start'] == []


async def test_named_call_task_resurrects_recorded_run(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A named task call resurrects an aborted run with its own options."""
    apify_client_async_patcher.patch('task', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', 'ABORTED'))
    apify_client_async_patcher.patch('run', 'resurrect', return_value=make_run('old-run', 'RUNNING'))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=make_run('old-run', 'SUCCEEDED'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run', actor_id=None, task_id='some-task')
        run = await Actor.call_task('some-task', run_name='scrape-eu', memory_mbytes=2048)

    assert run.id == 'old-run'
    assert apify_client_async_patcher.calls['task']['start'] == []
    [(_, kwargs)] = apify_client_async_patcher.calls['run']['resurrect']
    assert kwargs['memory_mbytes'] == 2048


async def test_named_call_task_rejects_name_recorded_for_actor(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """Reusing an Actor run's name for a task raises instead of attaching to the Actor's run."""
    apify_client_async_patcher.patch('task', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run')
        with pytest.raises(ValueError, match='already recorded for Actor "some-actor", it cannot be reused for task'):
            await Actor.call_task('some-task', run_name='scrape-eu')

    assert apify_client_async_patcher.calls['task']['start'] == []


async def test_registry_rejects_record_without_actor_or_task(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """A recorded run with neither an Actor nor a task ID is treated as a malformed registry."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run', actor_id=None)
        with pytest.raises(ValueError, match=CHILD_RUNS_KEY):
            await Actor.start('some-actor', run_name='scrape-eu')

    assert apify_client_async_patcher.calls['actor']['start'] == []


async def test_named_runs_forward_max_items_to_start(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """Named `start`, `call` and `call_task` pass `max_items` to the started run."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('task', 'start', return_value=make_run('new-task-run', 'READY'))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=make_run('new-run', 'SUCCEEDED'))

    async with Actor:
        await Actor.start('some-actor', run_name='started', max_items=10)
        await Actor.call('some-actor', run_name='called', max_items=20, logger=None)
        await Actor.call_task('some-task', run_name='task-called', max_items=30)

    assert [kwargs['max_items'] for _, kwargs in apify_client_async_patcher.calls['actor']['start']] == [10, 20]
    [(_, task_kwargs)] = apify_client_async_patcher.calls['task']['start']
    assert task_kwargs['max_items'] == 30


async def test_named_start_forwards_max_items_to_resurrect(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """A named start that resurrects the recorded run passes `max_items` to the resurrection."""
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', 'ABORTED'))
    apify_client_async_patcher.patch('run', 'resurrect', return_value=make_run('old-run', 'RUNNING'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run')
        await Actor.start('some-actor', run_name='scrape-eu', max_items=10)

    [(_, kwargs)] = apify_client_async_patcher.calls['run']['resurrect']
    assert kwargs['max_items'] == 10
