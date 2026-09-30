from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from apify_client._models import Run
from crawlee import service_locator
from crawlee.events import Event, EventAbortingData

from apify import Actor, Configuration
from apify._actor import _ActorType
from apify._child_runs import CHILD_RUNS_KEY, ChildRunRegistry
from apify.events import ApifyEventManager

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


@pytest.fixture
def apify_event_manager() -> ApifyEventManager:
    """Make the Actor use `ApifyEventManager`, which delivers `ABORTING` on the platform, without a websocket."""
    event_manager = ApifyEventManager(Configuration.get_global_configuration())
    service_locator.set_event_manager(event_manager)
    return event_manager


async def record_child_run(name: str, run_id: str, *, actor_id: str = 'some-actor') -> None:
    """Seed the registry the way an earlier attempt of this Actor run would have left it."""
    kvs = await Actor.open_key_value_store()
    await kvs.set_value(CHILD_RUNS_KEY, {name: {'actorId': actor_id, 'runId': run_id, 'previousRunIds': []}})


async def test_named_start_records_run_in_kvs(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A named start persists the name -> run ID entry to the default KVS as soon as the run starts."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor:
        run = await Actor.start('some-actor', name='scrape-eu')
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert run.id == 'new-run'
    assert stored == {
        'scrape-eu': {'actorId': 'some-actor', 'runId': 'new-run', 'previousRunIds': [], 'abortWithParent': False}
    }


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
        run = await Actor.start('some-actor', name='scrape-eu')

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
        run = await Actor.start('some-actor', name='scrape-eu', memory_mbytes=2048)

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
        run = await Actor.start('some-actor', name='scrape-eu')

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
        run = await Actor.start('some-actor', name='scrape-eu')
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert run.id == 'new-run'
    assert stored == {
        'scrape-eu': {
            'actorId': 'some-actor',
            'runId': 'new-run',
            'previousRunIds': ['old-run'],
            'abortWithParent': False,
        }
    }


async def test_named_start_rejects_name_recorded_for_another_actor(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """Reusing a name for a different Actor raises instead of attaching to the other Actor's run."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run', actor_id='other-actor')
        with pytest.raises(ValueError, match='already recorded for Actor "other-actor"'):
            await Actor.start('some-actor', name='scrape-eu')

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
        runs = await asyncio.gather(*(Actor.start('some-actor', name='scrape-eu') for _ in range(3)))

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
        runs = await asyncio.gather(*(actor.start('some-actor', name='scrape-eu') for _ in range(3)))

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
        run = await Actor.call('some-actor', name='scrape-eu')

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
        run = await Actor.call('some-actor', name='scrape-eu')

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
        run = await Actor.call('some-actor', name='scrape-eu')

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
        run = await Actor.call('some-actor', name='scrape-eu', timeout=timedelta(minutes=5))

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
        run = await Actor.call('some-actor', name='scrape-eu', logger=None)

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
            await Actor.start('some-actor', name='scrape-eu')

    assert apify_client_async_patcher.calls['actor']['start'] == []


async def test_child_runs_is_empty_without_named_runs(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """`Actor.child_runs` returns an empty dict and calls no API when nothing is recorded."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('new-run', 'READY'))

    async with Actor:
        await Actor.start('some-actor')
        child_runs = await Actor.child_runs()

    assert child_runs == {}
    assert apify_client_async_patcher.calls['run']['get'] == []


async def test_child_runs_returns_recorded_runs_with_current_state(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """`Actor.child_runs` returns each recorded run with its fetched state and history, `None` for a missing run."""
    runs = {'eu-run': make_run('eu-run', 'RUNNING'), 'us-run': None}

    async def get_run(run_client: Any, *_args: Any, **_kwargs: Any) -> Run | None:
        return runs[run_client.resource_id]

    apify_client_async_patcher.patch('run', 'get', replacement_method=get_run)

    async with Actor:
        kvs = await Actor.open_key_value_store()
        await kvs.set_value(
            CHILD_RUNS_KEY,
            {
                'scrape-eu': {'actorId': 'some-actor', 'runId': 'eu-run', 'previousRunIds': ['failed-run']},
                'scrape-us': {'actorId': 'other-actor', 'runId': 'us-run', 'previousRunIds': []},
            },
        )
        child_runs = await Actor.child_runs()

    assert child_runs.keys() == {'scrape-eu', 'scrape-us'}
    assert child_runs['scrape-eu'].actor_id == 'some-actor'
    assert child_runs['scrape-eu'].run_id == 'eu-run'
    assert child_runs['scrape-eu'].run == runs['eu-run']
    assert child_runs['scrape-eu'].previous_run_ids == ['failed-run']
    assert child_runs['scrape-us'].actor_id == 'other-actor'
    assert child_runs['scrape-us'].run is None


async def test_child_runs_includes_run_started_in_this_attempt(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """A run started by a named start in the same attempt shows up in `Actor.child_runs` right away."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('new-run', 'RUNNING'))

    async with Actor:
        await Actor.start('some-actor', name='scrape-eu')
        child_runs = await Actor.child_runs()

    assert child_runs['scrape-eu'].run_id == 'new-run'
    assert child_runs['scrape-eu'].run is not None
    assert child_runs['scrape-eu'].run.status == 'RUNNING'


@pytest.mark.parametrize(
    'method',
    [
        pytest.param('start', id='start'),
        pytest.param('call', id='call'),
    ],
)
async def test_abort_with_parent_requires_name(
    apify_client_async_patcher: ApifyClientAsyncPatcher, method: str
) -> None:
    """`abort_with_parent` without a `name` raises before any run is started."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('actor', 'call', return_value=make_run('new-run', 'SUCCEEDED'))

    async with Actor:
        with pytest.raises(ValueError, match='requires `name`'):
            await getattr(Actor, method)('some-actor', abort_with_parent=True)

    assert apify_client_async_patcher.calls['actor']['start'] == []
    assert apify_client_async_patcher.calls['actor']['call'] == []


async def test_named_start_records_abort_with_parent(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A named start with `abort_with_parent` records the flag with the run."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor:
        await Actor.start('some-actor', name='scrape-eu', abort_with_parent=True)
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert stored['scrape-eu']['abortWithParent'] is True


async def test_reattach_replaces_recorded_abort_with_parent(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """Reattaching under a name records the `abort_with_parent` value of the latest call."""
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', 'RUNNING'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run')
        await Actor.start('some-actor', name='scrape-eu', abort_with_parent=True)
        child_runs = await Actor.child_runs()

    assert child_runs['scrape-eu'].run_id == 'old-run'
    assert child_runs['scrape-eu'].abort_with_parent is True


async def test_aborting_event_aborts_marked_active_child_runs(
    apify_client_async_patcher: ApifyClientAsyncPatcher, apify_event_manager: ApifyEventManager
) -> None:
    """On `ABORTING`, only child runs marked `abort_with_parent` that are still active are gracefully aborted."""
    runs = {
        'running-run': make_run('running-run', 'RUNNING'),
        'ready-run': make_run('ready-run', 'READY'),
        'finished-run': make_run('finished-run', 'SUCCEEDED'),
        'unmarked-run': make_run('unmarked-run', 'RUNNING'),
    }

    async def get_run(run_client: Any, *_args: Any, **_kwargs: Any) -> Run | None:
        return runs[run_client.resource_id]

    apify_client_async_patcher.patch('run', 'get', replacement_method=get_run)
    apify_client_async_patcher.patch('run', 'abort', return_value=None)

    async with Actor:
        kvs = await Actor.open_key_value_store()
        await kvs.set_value(
            CHILD_RUNS_KEY,
            {
                name: {'actorId': 'some-actor', 'runId': run_id, 'previousRunIds': [], 'abortWithParent': marked}
                for name, run_id, marked in [
                    ('running', 'running-run', True),
                    ('ready', 'ready-run', True),
                    ('finished', 'finished-run', True),
                    ('unmarked', 'unmarked-run', False),
                ]
            },
        )
        apify_event_manager.emit(event=Event.ABORTING, event_data=EventAbortingData())
        await apify_event_manager.wait_for_all_listeners_to_complete()

    aborts = apify_client_async_patcher.calls['run']['abort']
    assert sorted(args[0].resource_id for args, _ in aborts) == ['ready-run', 'running-run']
    assert all(kwargs == {'gracefully': True} for _, kwargs in aborts)


async def test_failed_child_run_abort_does_not_stop_others(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
    caplog: pytest.LogCaptureFixture,
    apify_event_manager: ApifyEventManager,
) -> None:
    """A child run that fails to abort is logged, and the other marked child runs are still aborted."""

    async def abort_run(run_client: Any, *_args: Any, **_kwargs: Any) -> None:
        if run_client.resource_id == 'broken-run':
            raise RuntimeError('abort failed')

    apify_client_async_patcher.patch(
        'run', 'get', replacement_method=lambda run_client: make_run(run_client.resource_id, 'RUNNING')
    )
    apify_client_async_patcher.patch('run', 'abort', replacement_method=abort_run)

    async with Actor:
        kvs = await Actor.open_key_value_store()
        await kvs.set_value(
            CHILD_RUNS_KEY,
            {
                name: {'actorId': 'some-actor', 'runId': f'{name}-run', 'previousRunIds': [], 'abortWithParent': True}
                for name in ['broken', 'healthy']
            },
        )
        apify_event_manager.emit(event=Event.ABORTING, event_data=EventAbortingData())
        await apify_event_manager.wait_for_all_listeners_to_complete()

    aborts = apify_client_async_patcher.calls['run']['abort']
    assert sorted(args[0].resource_id for args, _ in aborts) == ['broken-run', 'healthy-run']
    assert 'Failed to abort child run "broken"' in caplog.text
    assert 'Aborted child run "healthy" with the parent' in caplog.text


async def test_child_run_is_aborted_with_the_client_it_was_started_with() -> None:
    """A child run started with its own client is aborted with that client, not the default one."""
    default_client = Mock()
    child_client = Mock()
    child_client.run.return_value.get = AsyncMock(return_value=make_run('new-run', 'RUNNING'))
    child_client.run.return_value.abort = AsyncMock()

    async with Actor:
        registry = ChildRunRegistry(Actor.open_key_value_store)
        await registry.find_or_start(
            'scrape-eu',
            actor_id='some-actor',
            client=child_client,
            start_run=AsyncMock(return_value=make_run('new-run', 'READY')),
            resurrect_run=AsyncMock(),
            abort_with_parent=True,
        )
        await registry.abort_runs_with_parent(default_client)

    child_client.run.return_value.abort.assert_awaited_once_with(gracefully=True)
    default_client.run.assert_not_called()


async def test_rejected_named_start_keeps_the_client_used_to_abort() -> None:
    """A named start rejected for another Actor does not change the client its recorded run is aborted with."""
    default_client = Mock()
    default_client.run.return_value.get = AsyncMock(return_value=make_run('old-run', 'RUNNING'))
    default_client.run.return_value.abort = AsyncMock()
    other_client = Mock()

    async with Actor:
        kvs = await Actor.open_key_value_store()
        await kvs.set_value(
            CHILD_RUNS_KEY,
            {'scrape-eu': {'actorId': 'some-actor', 'runId': 'old-run', 'previousRunIds': [], 'abortWithParent': True}},
        )
        registry = ChildRunRegistry(Actor.open_key_value_store)
        with pytest.raises(ValueError, match='cannot be reused'):
            await registry.find_or_start(
                'scrape-eu',
                actor_id='other-actor',
                client=other_client,
                start_run=AsyncMock(),
                resurrect_run=AsyncMock(),
            )
        await registry.abort_runs_with_parent(default_client)

    default_client.run.return_value.abort.assert_awaited_once_with(gracefully=True)
    other_client.run.assert_not_called()


async def test_aborting_waits_for_a_named_start_in_flight() -> None:
    """A named start in flight when the parent is aborted has its run aborted once the run is recorded."""
    client = Mock()
    client.run.return_value.get = AsyncMock(return_value=make_run('new-run', 'RUNNING'))
    client.run.return_value.abort = AsyncMock()
    started = asyncio.Event()
    release = asyncio.Event()

    async def start_run() -> Run:
        started.set()
        await release.wait()
        return make_run('new-run', 'READY')

    async with Actor:
        registry = ChildRunRegistry(Actor.open_key_value_store)
        start_task = asyncio.create_task(
            registry.find_or_start(
                'scrape-eu',
                actor_id='some-actor',
                client=client,
                start_run=start_run,
                resurrect_run=AsyncMock(),
                abort_with_parent=True,
            )
        )
        await started.wait()
        abort_task = asyncio.create_task(registry.abort_runs_with_parent(client))
        await asyncio.sleep(0)
        assert not abort_task.done()
        release.set()
        await asyncio.gather(start_task, abort_task)

    client.run.return_value.abort.assert_awaited_once_with(gracefully=True)


async def test_exit_removes_the_aborting_listener(
    apify_client_async_patcher: ApifyClientAsyncPatcher, apify_event_manager: ApifyEventManager
) -> None:
    """After the Actor exits, an `ABORTING` event on a still-active event manager aborts no child run."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('new-run', 'RUNNING'))
    apify_client_async_patcher.patch('run', 'abort', return_value=None)

    async with apify_event_manager:
        async with Actor:
            await Actor.start('some-actor', name='scrape-eu', abort_with_parent=True)
        apify_event_manager.emit(event=Event.ABORTING, event_data=EventAbortingData())
        await apify_event_manager.wait_for_all_listeners_to_complete()

    assert apify_client_async_patcher.calls['run']['abort'] == []


async def test_removing_all_aborting_listeners_keeps_aborting_child_runs(
    apify_client_async_patcher: ApifyClientAsyncPatcher, apify_event_manager: ApifyEventManager
) -> None:
    """Removing all `ABORTING` listeners from the event manager still aborts child runs marked `abort_with_parent`."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('new-run', 'RUNNING'))
    apify_client_async_patcher.patch('run', 'abort', return_value=None)

    async with Actor:
        await Actor.start('some-actor', name='scrape-eu', abort_with_parent=True)
        apify_event_manager.off(event=Event.ABORTING)
        apify_event_manager.emit(event=Event.ABORTING, event_data=EventAbortingData())
        await apify_event_manager.wait_for_all_listeners_to_complete()

    assert len(apify_client_async_patcher.calls['run']['abort']) == 1
