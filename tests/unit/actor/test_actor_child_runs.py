from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from apify_client._models import Run
from crawlee import service_locator
from crawlee.events import Event, EventAbortingData

from apify import Actor, Configuration
from apify._actor import _ActorType
from apify._charging import ChargingManagerImplementation
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
        'scrape-eu': {
            'actorId': 'some-actor',
            'runId': 'new-run',
            'previousRunIds': [],
            'abortWithParent': False,
            'maxTotalChargeUsd': None,
            'chargedUsd': None,
            'previousChargedUsd': '0',
        }
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
            'maxTotalChargeUsd': None,
            'chargedUsd': None,
            'previousChargedUsd': '0',
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

    async def start_run(*, max_total_charge_usd: Decimal | None) -> Run:  # noqa: ARG001
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


def make_client(statuses: dict[str, str]) -> Mock:
    """A client whose `run(run_id).get()` returns the run with its current status in `statuses`."""
    client = Mock()

    def run(run_id: str) -> Mock:
        run_client = Mock()
        run_client.get = AsyncMock(side_effect=lambda: make_run(run_id, statuses[run_id]))
        run_client.resurrect = AsyncMock(side_effect=lambda **_: make_run(run_id, 'RUNNING'))
        run_client.abort = AsyncMock()
        return run_client

    client.run.side_effect = run
    return client


async def start_child(
    registry: ChildRunRegistry, client: Mock, name: str, statuses: dict[str, str], *, run_id: str | None = None
) -> Run:
    """Start a named child run with the registry, adding its run to `statuses` as `RUNNING`."""

    async def start_run(*, max_total_charge_usd: Decimal | None) -> Run:  # noqa: ARG001
        new_run_id = run_id or f'{name}-run'
        statuses[new_run_id] = 'RUNNING'
        return make_run(new_run_id, 'READY')

    run, _ = await registry.find_or_start(
        name,
        actor_id='some-actor',
        client=client,
        start_run=start_run,
        resurrect_run=lambda run_client, max_total_charge_usd: run_client.resurrect(
            max_total_charge_usd=max_total_charge_usd
        ),
    )
    return run


async def assert_waiting(task: asyncio.Task) -> None:
    await asyncio.sleep(0.05)
    assert not task.done()


@pytest.mark.parametrize(
    'max_concurrent_runs',
    [
        pytest.param(0, id='zero'),
        pytest.param(-1, id='negative'),
    ],
)
async def test_set_child_run_limits_rejects_non_positive_limit(max_concurrent_runs: int) -> None:
    """A concurrency limit below 1 is rejected."""
    async with Actor:
        with pytest.raises(ValueError, match='must be at least 1'):
            Actor.set_child_run_limits(max_concurrent_runs=max_concurrent_runs)


async def test_named_start_waits_while_the_limit_is_reached() -> None:
    """A named start waits while the limit is reached and proceeds once an active child run finishes."""
    statuses: dict[str, str] = {}
    client = make_client(statuses)

    async with Actor:
        registry = ChildRunRegistry(Actor.open_key_value_store)
        registry.set_max_concurrent_runs(1)
        first = await start_child(registry, client, 'first', statuses)
        second_task = asyncio.create_task(start_child(registry, client, 'second', statuses))
        await assert_waiting(second_task)

        statuses[first.id] = 'SUCCEEDED'
        await registry.run_finished('first', make_run(first.id, 'SUCCEEDED'))
        second = await second_task

    assert second.id == 'second-run'


async def test_removing_the_limit_releases_waiting_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    """A named start waiting for a slot proceeds once the limit is removed."""
    monkeypatch.setattr('apify._child_runs._STATUS_MAX_AGE', timedelta(seconds=0.05))
    statuses: dict[str, str] = {}
    client = make_client(statuses)

    async with Actor:
        registry = ChildRunRegistry(Actor.open_key_value_store)
        registry.set_max_concurrent_runs(1)
        await start_child(registry, client, 'first', statuses)
        second_task = asyncio.create_task(start_child(registry, client, 'second', statuses))
        await assert_waiting(second_task)

        registry.set_max_concurrent_runs(None)
        second = await asyncio.wait_for(second_task, timeout=1)

    assert second.id == 'second-run'


async def test_stale_active_status_is_refreshed_before_counting(monkeypatch: pytest.MonkeyPatch) -> None:
    """A child run nobody awaited is fetched again once its status is stale, so a finished one frees its slot."""
    monkeypatch.setattr('apify._child_runs._STATUS_MAX_AGE', timedelta(0))
    statuses: dict[str, str] = {}
    client = make_client(statuses)

    async with Actor:
        registry = ChildRunRegistry(Actor.open_key_value_store)
        registry.set_max_concurrent_runs(1)
        first = await start_child(registry, client, 'first', statuses)
        second_task = asyncio.create_task(start_child(registry, client, 'second', statuses))
        await assert_waiting(second_task)

        statuses[first.id] = 'SUCCEEDED'
        second = await asyncio.wait_for(second_task, timeout=1)

    assert second.id == 'second-run'


async def test_child_run_recorded_by_an_earlier_attempt_counts_toward_the_limit() -> None:
    """An active child run recorded before a migration holds a slot, since it is fetched before it is counted."""
    statuses = {'old-run': 'RUNNING'}
    client = make_client(statuses)

    async with Actor:
        await record_child_run('first', 'old-run')
        registry = ChildRunRegistry(Actor.open_key_value_store)
        registry.set_max_concurrent_runs(1)
        second_task = asyncio.create_task(start_child(registry, client, 'second', statuses))
        await assert_waiting(second_task)
        second_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await second_task


async def test_child_run_that_cannot_be_fetched_does_not_block_the_limit() -> None:
    """A recorded child run whose fetch fails is not counted, so it does not fail or block a named start."""
    statuses: dict[str, str] = {}
    client = make_client(statuses)
    run_client_factory = client.run.side_effect

    def run(run_id: str) -> Mock:
        run_client = run_client_factory(run_id)
        if run_id == 'old-run':
            run_client.get = AsyncMock(side_effect=RuntimeError('forbidden'))
        return run_client

    client.run.side_effect = run

    async with Actor:
        await record_child_run('first', 'old-run')
        registry = ChildRunRegistry(Actor.open_key_value_store)
        registry.set_max_concurrent_runs(1)
        second = await asyncio.wait_for(start_child(registry, client, 'second', statuses), timeout=1)

    assert second.id == 'second-run'


async def test_listing_keeps_the_status_of_a_run_that_replaced_the_listed_one() -> None:
    """A run that replaces the listed one under a name keeps its slot after the listing observes the old run."""
    statuses = {'old-run': 'FAILED'}
    client = make_client(statuses)
    fetch_started = asyncio.Event()
    release_fetch = asyncio.Event()

    async def get_old_run() -> Run:
        fetch_started.set()
        await release_fetch.wait()
        return make_run('old-run', 'FAILED')

    list_client = Mock()
    list_client.run.return_value.get = AsyncMock(side_effect=get_old_run)

    async with Actor:
        await record_child_run('first', 'old-run')
        registry = ChildRunRegistry(Actor.open_key_value_store)
        registry.set_max_concurrent_runs(1)
        list_task = asyncio.create_task(registry.list_runs(list_client))
        await fetch_started.wait()
        await start_child(registry, client, 'first', statuses)
        release_fetch.set()
        await list_task

        second_task = asyncio.create_task(start_child(registry, client, 'second', statuses))
        await assert_waiting(second_task)
        second_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await second_task


async def test_reattach_does_not_wait_for_a_slot() -> None:
    """Reattaching to an active recorded child run returns it even while the limit is reached."""
    statuses = {'old-run': 'RUNNING'}
    client = make_client(statuses)

    async with Actor:
        await record_child_run('first', 'old-run')
        registry = ChildRunRegistry(Actor.open_key_value_store)
        registry.set_max_concurrent_runs(1)
        run = await asyncio.wait_for(start_child(registry, client, 'first', statuses), timeout=1)

    assert run.id == 'old-run'


async def test_resurrection_waits_for_a_slot() -> None:
    """Resurrecting an aborted child run waits while the limit is reached."""
    statuses = {'old-run': 'ABORTED'}
    client = make_client(statuses)

    async with Actor:
        await record_child_run('first', 'old-run')
        registry = ChildRunRegistry(Actor.open_key_value_store)
        registry.set_max_concurrent_runs(1)
        second = await start_child(registry, client, 'second', statuses)
        first_task = asyncio.create_task(start_child(registry, client, 'first', statuses))
        await assert_waiting(first_task)

        statuses[second.id] = 'SUCCEEDED'
        await registry.run_finished('second', make_run(second.id, 'SUCCEEDED'))
        first = await first_task

    assert first.id == 'old-run'
    assert first.status == 'RUNNING'


async def test_concurrent_named_starts_respect_the_limit() -> None:
    """Concurrent named starts under different names start no more runs than the limit."""
    statuses: dict[str, str] = {}
    client = make_client(statuses)

    async with Actor:
        registry = ChildRunRegistry(Actor.open_key_value_store)
        registry.set_max_concurrent_runs(2)
        tasks = [asyncio.create_task(start_child(registry, client, f'child-{i}', statuses)) for i in range(3)]
        await asyncio.sleep(0.05)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    assert sum(task.cancelled() for task in tasks) == 1
    assert len(statuses) == 2


async def test_failed_start_releases_its_slot() -> None:
    """A named start that raises frees its slot for the next one."""
    statuses: dict[str, str] = {}
    client = make_client(statuses)

    async with Actor:
        registry = ChildRunRegistry(Actor.open_key_value_store)
        registry.set_max_concurrent_runs(1)
        with pytest.raises(RuntimeError, match='start failed'):
            await registry.find_or_start(
                'first',
                actor_id='some-actor',
                client=client,
                start_run=AsyncMock(side_effect=RuntimeError('start failed')),
                resurrect_run=AsyncMock(),
            )
        second = await asyncio.wait_for(start_child(registry, client, 'second', statuses), timeout=1)

    assert second.id == 'second-run'


async def test_parent_abort_stops_starts_waiting_for_a_slot() -> None:
    """A named start waiting for a slot raises once the parent is aborted, without starting a run."""
    statuses: dict[str, str] = {}
    client = make_client(statuses)

    async with Actor:
        registry = ChildRunRegistry(Actor.open_key_value_store)
        registry.set_max_concurrent_runs(1)
        await start_child(registry, client, 'first', statuses)
        second_task = asyncio.create_task(start_child(registry, client, 'second', statuses))
        await assert_waiting(second_task)

        await asyncio.wait_for(registry.abort_runs_with_parent(client), timeout=1)
        with pytest.raises(RuntimeError, match='being aborted'):
            await second_task

    assert 'second-run' not in statuses


async def test_named_call_frees_its_slot_when_the_run_finishes(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """A child run awaited by a named call to its end frees its slot without being fetched again."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    # A fetch would report the run as still running, so only the awaited status can free the slot.
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('new-run', 'RUNNING'))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=make_run('new-run', 'SUCCEEDED'))

    async with Actor:
        Actor.set_child_run_limits(max_concurrent_runs=1)
        await Actor.call('some-actor', name='first', logger=None)
        await asyncio.wait_for(Actor.start('some-actor', name='second'), timeout=1)

    assert len(apify_client_async_patcher.calls['actor']['start']) == 2


@pytest.fixture
def parent_budget(
    monkeypatch: pytest.MonkeyPatch, apify_client_async_patcher: ApifyClientAsyncPatcher
) -> dict[str, Run]:
    """Give the Actor run a budget of 10 USD, with each local charge costing 1 USD, and a client serving `runs`."""
    monkeypatch.setenv('ACTOR_MAX_TOTAL_CHARGE_USD', '10')
    monkeypatch.setenv('ACTOR_TEST_PAY_PER_EVENT', 'true')
    runs: dict[str, Run] = {}

    def start(*_args: Any, **_kwargs: Any) -> Run:
        run = make_run(f'run-{len(runs) + 1}', 'READY')
        runs[run.id] = run.model_copy(update={'status': 'RUNNING'})
        return run

    apify_client_async_patcher.patch('actor', 'start', replacement_method=start)
    apify_client_async_patcher.patch(
        'run', 'get', replacement_method=lambda run_client: runs.get(run_client._resource_id)
    )
    apify_client_async_patcher.patch(
        'run', 'resurrect', replacement_method=lambda run_client, **_: runs[run_client._resource_id]
    )
    return runs


def finish(run: Run, status: str, usage_total_usd: float, *, finished_ago: timedelta = timedelta(0)) -> Run:
    return run.model_copy(
        update={
            'status': status,
            'usage_total_usd': usage_total_usd,
            'finished_at': datetime.now(UTC) - finished_ago,
        }
    )


def started_limits(apify_client_async_patcher: ApifyClientAsyncPatcher) -> list[Decimal | None]:
    return [kwargs['max_total_charge_usd'] for _, kwargs in apify_client_async_patcher.calls['actor']['start']]


@pytest.mark.usefixtures('parent_budget')
async def test_named_start_gets_the_budget_left(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A named start without a charge limit gets the part of the parent's budget it has not charged itself."""
    async with Actor:
        await Actor.charge('some-event', count=3)
        await Actor.start('some-actor', name='child')

    assert started_limits(apify_client_async_patcher) == [Decimal(7)]


@pytest.mark.parametrize(
    ('requested', 'expected'),
    [
        pytest.param(Decimal(4), Decimal(4), id='within budget'),
        pytest.param(Decimal(20), Decimal(10), id='above budget'),
    ],
)
@pytest.mark.usefixtures('parent_budget')
async def test_named_start_charge_limit_is_capped_at_the_budget_left(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
    requested: Decimal,
    expected: Decimal,
) -> None:
    """An explicit charge limit of a named start is kept within the budget left and lowered above it."""
    async with Actor:
        await Actor.start('some-actor', name='child', max_total_charge_usd=requested)

    assert started_limits(apify_client_async_patcher) == [expected]


@pytest.mark.usefixtures('parent_budget')
async def test_unnamed_start_charge_limit_is_passed_through(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """A start without a name is not tracked, so its charge limit is neither capped nor reserved."""
    async with Actor:
        await Actor.start('some-actor', max_total_charge_usd=Decimal(20))
        await Actor.start('some-actor', name='child')

    assert started_limits(apify_client_async_patcher) == [Decimal(20), Decimal(10)]


async def test_named_start_charge_limit_is_passed_through_without_a_parent_budget(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """Without a parent budget, a named start gets the charge limit it asked for."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor:
        await Actor.start('some-actor', name='first', max_total_charge_usd=Decimal(20))
        await Actor.start('some-actor', name='second')

    assert started_limits(apify_client_async_patcher) == [Decimal(20), None]


@pytest.mark.usefixtures('parent_budget')
async def test_running_child_run_reserves_its_charge_limit(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """The limit of a running child run is reserved, both from later child runs and from the parent's own charges."""
    async with Actor:
        await Actor.start('some-actor', name='first', max_total_charge_usd=Decimal(6))
        charge_result = await Actor.charge('some-event', count=3)
        await Actor.start('some-actor', name='second')

    assert charge_result.charged_count == 3
    assert started_limits(apify_client_async_patcher) == [Decimal(6), Decimal(1)]


@pytest.mark.usefixtures('parent_budget')
async def test_reserved_budget_limits_the_parent_charges() -> None:
    """The parent charges only the part of its budget not reserved for child runs."""
    async with Actor:
        await Actor.start('some-actor', name='child', max_total_charge_usd=Decimal(6))
        charge_result = await Actor.charge('some-event', count=10)

    assert charge_result.charged_count == 4


@pytest.mark.usefixtures('parent_budget')
async def test_exhausted_budget_rejects_a_named_start() -> None:
    """A named start raises when the whole parent budget is charged or reserved."""
    async with Actor:
        await Actor.start('some-actor', name='first')
        with pytest.raises(RuntimeError, match='budget of this Actor run is spent or reserved'):
            await Actor.start('some-actor', name='second')


@pytest.mark.usefixtures('parent_budget')
async def test_concurrent_named_starts_share_the_budget() -> None:
    """Concurrent named starts reserve their limits one at a time, so together they stay within the budget."""
    async with Actor:
        results = await asyncio.gather(
            *(Actor.start('some-actor', name=name, max_total_charge_usd=Decimal(6)) for name in ('a', 'b')),
            return_exceptions=True,
        )
        child_runs = await Actor.child_runs()

    assert not any(isinstance(result, BaseException) for result in results)
    assert sorted(info.max_total_charge_usd or Decimal(0) for info in child_runs.values()) == [Decimal(4), Decimal(6)]


async def test_finished_child_run_releases_its_unused_budget(
    parent_budget: dict[str, Run], apify_client_async_patcher: ApifyClientAsyncPatcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A finished child run keeps only its charge reserved, and records it once it can no longer change."""
    monkeypatch.setattr('apify._child_runs._STATUS_MAX_AGE', timedelta(0))
    async with Actor:
        first = await Actor.start('some-actor', name='first', max_total_charge_usd=Decimal(6))
        parent_budget[first.id] = finish(parent_budget[first.id], 'SUCCEEDED', 2)
        await Actor.start('some-actor', name='second', max_total_charge_usd=Decimal(3))
        parent_budget['run-2'] = finish(parent_budget['run-2'], 'SUCCEEDED', 1, finished_ago=timedelta(minutes=5))
        await Actor.start('some-actor', name='third')
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert started_limits(apify_client_async_patcher) == [Decimal(6), Decimal(3), Decimal(7)]
    # The first run finished just now, so the platform may still add to its charge.
    assert stored['first']['chargedUsd'] is None
    assert stored['second']['chargedUsd'] == '1'


async def seed_budget_record(name: str, run_id: str, **fields: Any) -> None:
    """Seed the registry with a record carrying budget fields, as an earlier attempt of this Actor run would."""
    kvs = await Actor.open_key_value_store()
    await kvs.set_value(
        CHILD_RUNS_KEY, {name: {'actorId': 'some-actor', 'runId': run_id, 'previousRunIds': [], **fields}}
    )


@pytest.mark.usefixtures('parent_budget')
async def test_reservations_of_an_earlier_attempt_limit_the_parent_charges() -> None:
    """A child run recorded by an earlier attempt of the parent keeps its limit reserved from the parent's charges."""
    async with Actor:
        await seed_budget_record('child', 'old-run', maxTotalChargeUsd='6')

    # A fresh instance, as the parent is after a migration or resurrection.
    async with _ActorType() as actor:
        charge_result = await actor.charge('some-event', count=10)

    assert charge_result.charged_count == 4


async def test_resurrection_reuses_the_reservation_of_its_run(
    parent_budget: dict[str, Run], apify_client_async_patcher: ApifyClientAsyncPatcher
) -> None:
    """A resurrected run gets the budget left plus its own reservation, since its limit covers its earlier charges."""
    parent_budget['old-run'] = finish(make_run('old-run', 'RUNNING'), 'ABORTED', 1)
    parent_budget['other-run'] = make_run('other-run', 'RUNNING')

    async with Actor:
        kvs = await Actor.open_key_value_store()
        await kvs.set_value(
            CHILD_RUNS_KEY,
            {
                'child': {'actorId': 'some-actor', 'runId': 'old-run', 'maxTotalChargeUsd': '6'},
                'other': {'actorId': 'some-actor', 'runId': 'other-run', 'maxTotalChargeUsd': '3'},
            },
        )

    async with _ActorType() as actor:
        await actor.start('some-actor', name='child')

    [(_, kwargs)] = apify_client_async_patcher.calls['run']['resurrect']
    assert kwargs['max_total_charge_usd'] == Decimal(7)


async def test_replaced_failed_run_keeps_its_charge_reserved(
    parent_budget: dict[str, Run], apify_client_async_patcher: ApifyClientAsyncPatcher
) -> None:
    """A failed run replaced by a new one under the same name keeps its charge counted against the budget."""
    parent_budget['old-run'] = finish(make_run('old-run', 'RUNNING'), 'FAILED', 3, finished_ago=timedelta(minutes=5))

    async with Actor:
        await seed_budget_record('child', 'old-run', maxTotalChargeUsd='6')

    async with _ActorType() as actor:
        await actor.start('some-actor', name='child')
        kvs = await actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert started_limits(apify_client_async_patcher) == [Decimal(7)]
    assert stored['child']['previousChargedUsd'] == '3'
    assert stored['child']['maxTotalChargeUsd'] == '7'


@pytest.mark.usefixtures('parent_budget')
async def test_failed_named_start_releases_its_reservation(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A named start that fails leaves no part of the budget reserved."""
    async with Actor:
        apify_client_async_patcher.patch('actor', 'start', replacement_method=Mock(side_effect=RuntimeError('boom')))
        with pytest.raises(RuntimeError, match='boom'):
            await Actor.start('some-actor', name='child')
        charge_result = await Actor.charge('some-event', count=10)

    assert charge_result.charged_count == 10


async def test_named_start_in_flight_reserves_its_limit(
    parent_budget: dict[str, Run], apify_client_async_patcher: ApifyClientAsyncPatcher
) -> None:
    """The limit of a named start in flight is reserved before the platform returns its run."""
    started = asyncio.Event()
    release = asyncio.Event()

    async def start(*_args: Any, **_kwargs: Any) -> Run:
        started.set()
        await release.wait()
        run = make_run('slow-run', 'READY')
        parent_budget[run.id] = run
        return run

    async with Actor:
        apify_client_async_patcher.patch('actor', 'start', replacement_method=start)
        start_task = asyncio.create_task(Actor.start('some-actor', name='first'))
        await started.wait()
        charge_result = await Actor.charge('some-event', count=1)
        release.set()
        await start_task

    assert charge_result.charged_count == 0


async def test_listing_child_runs_releases_the_unused_budget(parent_budget: dict[str, Run]) -> None:
    """Listing the child runs releases the unused limit of those that finished."""
    async with Actor:
        run = await Actor.start('some-actor', name='child', max_total_charge_usd=Decimal(6))
        parent_budget[run.id] = finish(parent_budget[run.id], 'SUCCEEDED', 2)
        await Actor.child_runs()
        charge_result = await Actor.charge('some-event', count=10)

    assert charge_result.charged_count == 8


async def test_named_call_releases_the_unused_budget_when_the_run_finishes(
    parent_budget: dict[str, Run], apify_client_async_patcher: ApifyClientAsyncPatcher
) -> None:
    """A named call releases the unused limit of its run once the run finishes."""
    apify_client_async_patcher.patch(
        'run',
        'wait_for_finish',
        replacement_method=lambda run_client, **_: finish(parent_budget[run_client._resource_id], 'SUCCEEDED', 2),
    )

    async with Actor:
        await Actor.call('some-actor', name='child', max_total_charge_usd=Decimal(6), logger=None)
        charge_result = await Actor.charge('some-event', count=10)

    assert charge_result.charged_count == 8


@pytest.mark.usefixtures('parent_budget')
async def test_platform_default_charge_limit_is_not_shared_with_child_runs(
    apify_client_async_patcher: ApifyClientAsyncPatcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A limit the platform gave the parent by default is not split among its child runs."""
    monkeypatch.setattr(
        ChargingManagerImplementation, 'is_max_total_charge_usd_set_by_user', AsyncMock(return_value=False)
    )

    async with Actor:
        await Actor.start('some-actor', name='first')
        await Actor.start('some-actor', name='second', max_total_charge_usd=Decimal(20))
        charge_result = await Actor.charge('some-event', count=10)

    assert started_limits(apify_client_async_patcher) == [None, Decimal(20)]
    assert charge_result.charged_count == 10


async def test_run_fetched_before_its_resurrection_keeps_the_reservation(
    parent_budget: dict[str, Run], apify_client_async_patcher: ApifyClientAsyncPatcher
) -> None:
    """A snapshot of a run fetched before its resurrection does not release the limit of the resurrected run."""
    parent_budget['old-run'] = finish(make_run('old-run', 'RUNNING'), 'ABORTED', 1, finished_ago=timedelta(minutes=5))
    listing = asyncio.Event()
    release = asyncio.Event()

    async def get(run_client: Any) -> Run | None:
        run = parent_budget.get(run_client._resource_id)
        if not listing.is_set():
            listing.set()
            await release.wait()
        return run

    def resurrect(run_client: Any, **_: Any) -> Run:
        run = parent_budget[run_client._resource_id].model_copy(update={'status': 'RUNNING', 'finished_at': None})
        parent_budget[run.id] = run
        return run

    async with Actor:
        await seed_budget_record('child', 'old-run', maxTotalChargeUsd='6')

    apify_client_async_patcher.patch('run', 'get', replacement_method=get, is_async=True)
    apify_client_async_patcher.patch('run', 'resurrect', replacement_method=resurrect, is_async=True)

    async with _ActorType() as actor:
        list_task = asyncio.create_task(actor.child_runs())
        await listing.wait()
        await actor.start('some-actor', name='child')
        release.set()
        await list_task
        charge_result = await actor.charge('some-event', count=10)

    assert charge_result.charged_count == 0


async def test_resurrection_in_flight_reserves_its_limit_once(
    parent_budget: dict[str, Run], apify_client_async_patcher: ApifyClientAsyncPatcher
) -> None:
    """While a resurrection is in flight, its limit is reserved once, including the charge its run made before."""
    parent_budget['old-run'] = finish(make_run('old-run', 'RUNNING'), 'ABORTED', 1, finished_ago=timedelta(minutes=5))
    started = asyncio.Event()
    release = asyncio.Event()

    async def resurrect(run_client: Any, **_: Any) -> Run:
        started.set()
        await release.wait()
        return parent_budget[run_client._resource_id].model_copy(update={'status': 'RUNNING', 'finished_at': None})

    async with Actor:
        await seed_budget_record('child', 'old-run', maxTotalChargeUsd='6')

    apify_client_async_patcher.patch('run', 'resurrect', replacement_method=resurrect, is_async=True)

    async with _ActorType() as actor:
        start_task = asyncio.create_task(actor.start('some-actor', name='child', max_total_charge_usd=Decimal(4)))
        await started.wait()
        charge_result = await actor.charge('some-event', count=10)
        release.set()
        await start_task

    assert charge_result.charged_count == 6


async def test_failed_resurrection_leaves_the_charge_of_its_run_to_settle(
    parent_budget: dict[str, Run], apify_client_async_patcher: ApifyClientAsyncPatcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A resurrection that fails does not stop the charge of the finished run from being recorded later."""
    parent_budget['old-run'] = finish(make_run('old-run', 'RUNNING'), 'ABORTED', 1)

    async with Actor:
        await seed_budget_record('child', 'old-run', maxTotalChargeUsd='6')

    apify_client_async_patcher.patch('run', 'resurrect', replacement_method=Mock(side_effect=RuntimeError('boom')))

    async with _ActorType() as actor:
        with pytest.raises(RuntimeError, match='boom'):
            await actor.start('some-actor', name='child')
        monkeypatch.setattr('apify._child_runs._CHARGE_SETTLE_TIME', timedelta(0))
        await actor.child_runs()
        kvs = await actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert stored['child']['chargedUsd'] == '1'
