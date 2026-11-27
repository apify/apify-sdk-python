from __future__ import annotations

import asyncio
import hashlib
import io
import warnings
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from pydantic import ValidationError

from apify_client._models import Run
from apify_client.errors import NotFoundError
from crawlee import service_locator
from crawlee.events import Event, EventAbortingData

from apify import Actor, Configuration, Webhook, _child_runs
from apify._actor import _ActorType
from apify._child_runs import (
    CHILD_RUNS_KEY,
    ChildRun,
    ChildRunRecord,
    ChildRunRegistry,
    ChildRunTracker,
    KeyValueStoreChildRunTracker,
    checksum_request,
    checksum_run_options,
    name_key,
)
from apify._webhook import to_client_representations
from apify.events import ApifyEventManager

if TYPE_CHECKING:
    from apify_client import ApifyClientAsync

    from ..conftest import ApifyClientAsyncPatcher
    from apify.storages import KeyValueStore


pytestmark = pytest.mark.filterwarnings('ignore:Child run features:UserWarning')


def make_run(run_id: str, status: str) -> Run:
    return Run.model_validate(
        {
            'id': run_id,
            'actId': 'actor_id',
            'userId': 'user_id',
            'startedAt': STARTED_AT,
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


STARTED_AT = '2024-08-08T12:12:44Z'


def stored_record(
    run_id: str,
    status: str,
    *,
    actor_id: str | None = 'some-actor',
    task_id: str | None = None,
    run_input: Any = None,
    options: dict[str, Any] | None = None,
    abort_with_parent: bool = False,
) -> dict[str, Any]:
    """Build the registry record of a named run as it is stored in the default KVS."""
    return {
        'runId': run_id,
        'status': status,
        'abortWithParent': abort_with_parent,
        'checksum': checksum_request(actor_id=actor_id, task_id=task_id, run_input=run_input, options=options),
    }


def stored_registry(
    named: dict[str, dict[str, Any]] | None = None, runs: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Build the registry value as it is stored in the default KVS, from named records and records by their key."""
    named_runs = {name_key(name): record for name, record in (named or {}).items()}
    return {'runs': {**named_runs, **(runs or {})}}


def named_child_runs(child_runs: list[ChildRun]) -> dict[str, ChildRun]:
    """Return the entries of `Actor.child_runs` started with a run name, by that name."""
    return {
        child_run.key.removeprefix('name:'): child_run for child_run in child_runs if child_run.key.startswith('name:')
    }


@pytest.fixture
def apify_event_manager() -> ApifyEventManager:
    """Make the Actor use `ApifyEventManager`, which delivers `ABORTING` on the platform, without a websocket."""
    event_manager = ApifyEventManager(Configuration.get_global_configuration())
    service_locator.set_event_manager(event_manager)
    return event_manager


async def record_child_run(
    name: str,
    run_id: str,
    *,
    actor_id: str | None = 'some-actor',
    task_id: str | None = None,
    run_input: Any = None,
    options: dict[str, Any] | None = None,
) -> None:
    """Seed the registry the way an earlier process of this Actor run would have left it, and reload it like init."""
    kvs = await Actor.open_key_value_store()
    record = stored_record(run_id, 'RUNNING', actor_id=actor_id, task_id=task_id, run_input=run_input, options=options)
    await kvs.set_value(CHILD_RUNS_KEY, stored_registry({name: record}))
    await Actor._child_run_registry.load()


async def test_named_start_records_run_in_kvs(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A named start persists the name -> run ID entry to the default KVS as soon as the run starts."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor:
        run = await Actor.start('some-actor', run_name='scrape-eu')
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert run.id == 'new-run'
    assert stored == stored_registry({'scrape-eu': stored_record('new-run', 'READY')})


@pytest.mark.parametrize(
    ('method', 'resource'),
    [
        pytest.param('start', 'actor', id='start'),
        pytest.param('call', 'actor', id='call'),
        pytest.param('start_task', 'task', id='start task'),
        pytest.param('call_task', 'task', id='call task'),
    ],
)
async def test_unnamed_run_is_recorded_under_its_run_id(
    apify_client_async_patcher: ApifyClientAsyncPatcher, method: str, resource: str
) -> None:
    """A run started without a name is recorded under `run:<run ID>`, and a call records its final status."""
    apify_client_async_patcher.patch(resource, 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=make_run('new-run', 'SUCCEEDED'))

    async with Actor:
        kwargs = {'logger': None} if method.startswith('call') else {}
        await getattr(Actor, method)('some-id', **kwargs)
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    status = 'SUCCEEDED' if method.startswith('call') else 'READY'
    assert stored == {'runs': {'run:new-run': {'runId': 'new-run', 'status': status, 'abortWithParent': False}}}


async def test_unnamed_runs_with_the_same_request_are_separate(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """Two starts without a name start two runs, both listed in `Actor.child_runs` in the order they were started."""
    runs = iter([make_run('first-run', 'READY'), make_run('second-run', 'READY')])
    apify_client_async_patcher.patch('actor', 'start', replacement_method=lambda *_args, **_kwargs: next(runs))

    async with Actor:
        await Actor.start('some-actor', {'q': 1})
        await Actor.start('some-actor', {'q': 1})
        keys = [child_run.key for child_run in Actor.child_runs]

    assert keys == ['run:first-run', 'run:second-run']


@pytest.mark.parametrize(
    'status',
    [
        pytest.param('READY', id='ready'),
        pytest.param('RUNNING', id='running'),
        pytest.param('SUCCEEDED', id='succeeded'),
        pytest.param('FAILED', id='failed'),
        pytest.param('ABORTING', id='aborting'),
        pytest.param('ABORTED', id='aborted'),
        pytest.param('TIMING-OUT', id='timing out'),
        pytest.param('TIMED-OUT', id='timed out'),
    ],
)
async def test_named_start_returns_recorded_run_in_any_status(
    apify_client_async_patcher: ApifyClientAsyncPatcher, status: str
) -> None:
    """A recorded run is returned in the status it is in, without starting, resurrecting or waiting for a run."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', status))
    apify_client_async_patcher.patch('run', 'resurrect', return_value=make_run('old-run', 'RUNNING'))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=make_run('old-run', 'SUCCEEDED'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run')
        run = await Actor.start('some-actor', run_name='scrape-eu')

    assert run.id == 'old-run'
    assert run.status == status
    assert apify_client_async_patcher.calls['actor']['start'] == []
    assert apify_client_async_patcher.calls['run']['resurrect'] == []
    assert apify_client_async_patcher.calls['run']['wait_for_finish'] == []


async def test_named_start_replaces_missing_run(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A recorded run that no longer exists is replaced by a new run under the same name, with a warning."""
    monkeypatch.setattr(_child_runs, '_NOT_FOUND_GRACE_SECS', 0)
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=None)

    async with Actor:
        await record_child_run('scrape-eu', 'old-run')
        run = await Actor.start('some-actor', run_name='scrape-eu')
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)
        child_runs = Actor.child_runs

    assert run.id == 'new-run'
    assert stored == stored_registry({'scrape-eu': stored_record('new-run', 'READY')})
    assert named_child_runs(child_runs)['scrape-eu'].client.resource_id == 'new-run'
    [warning] = [record for record in caplog.records if record.levelname == 'WARNING']
    assert 'Child run "name:scrape-eu" no longer exists' in warning.getMessage()
    assert warning.__dict__['run_id'] == 'old-run'


async def test_named_start_rejects_name_recorded_for_another_actor(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """Reusing a name for a different Actor raises instead of attaching to the other Actor's run."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', 'RUNNING'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run', actor_id='other-actor')
        with pytest.raises(ValueError, match='already used for a different Actor, task, input or run options'):
            await Actor.start('some-actor', run_name='scrape-eu')

    assert apify_client_async_patcher.calls['actor']['start'] == []


async def test_named_start_rejects_name_recorded_for_task(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """Reusing a task run's name for an Actor raises instead of attaching to the task's run."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', 'RUNNING'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run', actor_id=None, task_id='some-task')
        with pytest.raises(ValueError, match='already used for a different Actor, task, input or run options'):
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


@pytest.mark.parametrize(
    'status',
    [
        pytest.param('SUCCEEDED', id='succeeded'),
        pytest.param('FAILED', id='failed'),
        pytest.param('ABORTED', id='aborted'),
        pytest.param('TIMED-OUT', id='timed out'),
    ],
)
async def test_named_call_returns_finished_run_without_waiting(
    apify_client_async_patcher: ApifyClientAsyncPatcher, status: str
) -> None:
    """A named call whose recorded run already finished returns it without waiting or streaming logs."""
    get_streamed_log = Mock(return_value=MagicMock())
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', status))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=None)
    apify_client_async_patcher.patch('run', 'get_streamed_log', replacement_method=get_streamed_log)

    async with Actor:
        await record_child_run('scrape-eu', 'old-run')
        run = await Actor.call('some-actor', run_name='scrape-eu')

    assert run.id == 'old-run'
    assert run.status == status
    assert apify_client_async_patcher.calls['run']['wait_for_finish'] == []
    get_streamed_log.assert_not_called()


@pytest.mark.parametrize(
    ('status', 'finished_status'),
    [
        pytest.param('ABORTING', 'ABORTED', id='aborting'),
        pytest.param('TIMING-OUT', 'TIMED-OUT', id='timing out'),
    ],
)
async def test_named_call_waits_for_settling_run(
    apify_client_async_patcher: ApifyClientAsyncPatcher, status: str, finished_status: str
) -> None:
    """A named call whose recorded run is aborting or timing out waits for it and returns it finished."""
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', status))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=make_run('old-run', finished_status))
    apify_client_async_patcher.patch('run', 'resurrect', return_value=make_run('old-run', 'RUNNING'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run')
        run = await Actor.call('some-actor', run_name='scrape-eu', logger=None)
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert run.status == finished_status
    assert stored['runs']['name:scrape-eu']['status'] == finished_status
    assert apify_client_async_patcher.calls['run']['resurrect'] == []


async def test_named_call_returns_active_run_when_wait_runs_out(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """A named call whose `wait` runs out returns the run in its current status."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=make_run('new-run', 'RUNNING'))

    async with Actor:
        run = await Actor.call('some-actor', run_name='scrape-eu', wait=timedelta(seconds=1), logger=None)
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert run.status == 'RUNNING'
    assert stored['runs']['name:scrape-eu']['status'] == 'RUNNING'
    [(_, kwargs)] = apify_client_async_patcher.calls['run']['wait_for_finish']
    assert kwargs['wait_duration'] == timedelta(seconds=1)


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


async def test_init_rejects_malformed_registry() -> None:
    """Init raises a `ValueError` naming the key when the registry in the default KVS is malformed, and tears down."""
    async with Actor:
        kvs = await Actor.open_key_value_store()
        await kvs.set_value(CHILD_RUNS_KEY, stored_registry({'scrape-eu': {'runId': 'old-run'}}))

    with pytest.raises(ValueError, match=CHILD_RUNS_KEY):
        await Actor.init()

    assert not Actor._active
    assert not Actor.event_manager.active


async def test_init_does_not_read_the_actor_child_runs_key() -> None:
    """A value under the `__ACTOR_CHILD_RUNS` key is not read as the registry."""
    async with Actor:
        kvs = await Actor.open_key_value_store()
        await kvs.set_value('__ACTOR_CHILD_RUNS', {'scrape-eu': {'runId': 'old-run'}})

    async with Actor:
        child_runs = Actor.child_runs

    assert child_runs == []


async def test_named_call_task_records_run_in_kvs(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A named task call starts the task, records the run under the task ID, and waits for it."""
    apify_client_async_patcher.patch('task', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=make_run('new-run', 'SUCCEEDED'))

    async with Actor:
        run = await Actor.call_task('some-task', run_name='scrape-eu', logger=None)
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert run.status == 'SUCCEEDED'
    assert stored == stored_registry(
        {'scrape-eu': stored_record('new-run', 'SUCCEEDED', actor_id=None, task_id='some-task')}
    )
    assert apify_client_async_patcher.calls['task']['call'] == []


async def test_named_call_task_waits_for_reattached_run(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A named task call waits for the recorded running run without starting the task again."""
    apify_client_async_patcher.patch('task', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', 'RUNNING'))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=make_run('old-run', 'SUCCEEDED'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run', actor_id=None, task_id='some-task')
        run = await Actor.call_task('some-task', run_name='scrape-eu', logger=None)

    assert run.id == 'old-run'
    assert run.status == 'SUCCEEDED'
    assert apify_client_async_patcher.calls['task']['start'] == []


@pytest.mark.parametrize(
    ('is_recorded', 'from_start'),
    [
        pytest.param(False, True, id='new run'),
        pytest.param(True, False, id='reattached run'),
    ],
)
async def test_named_call_task_streams_run_log(
    apify_client_async_patcher: ApifyClientAsyncPatcher, *, is_recorded: bool, from_start: bool
) -> None:
    """A named task call streams the log of a new run from the start, and only the new lines of a reattached run."""
    streamed_log = MagicMock()
    get_streamed_log = Mock(return_value=streamed_log)
    apify_client_async_patcher.patch('task', 'start', return_value=make_run('some-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('some-run', 'RUNNING'))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=make_run('some-run', 'SUCCEEDED'))
    apify_client_async_patcher.patch('run', 'get_status_message_watcher', return_value=MagicMock())
    apify_client_async_patcher.patch('run', 'get_streamed_log', replacement_method=get_streamed_log)

    async with Actor:
        if is_recorded:
            await record_child_run('scrape-eu', 'some-run', actor_id=None, task_id='some-task')
        run = await Actor.call_task('some-task', run_name='scrape-eu')

    assert run.status == 'SUCCEEDED'
    assert get_streamed_log.call_args.kwargs['from_start'] is from_start
    streamed_log.__aenter__.assert_awaited_once()


@pytest.mark.parametrize(
    ('method', 'resource'),
    [
        pytest.param('call', 'actor', id='call'),
        pytest.param('call_task', 'task', id='call task'),
    ],
)
async def test_concurrent_named_calls_redirect_the_run_log_once(
    apify_client_async_patcher: ApifyClientAsyncPatcher, method: str, resource: str
) -> None:
    """Concurrent calls under one name share one run, and only one of them redirects its log."""
    get_streamed_log = Mock(return_value=MagicMock())

    async def wait_for_finish(*_args: Any, **_kwargs: Any) -> Run:
        await asyncio.sleep(0.05)
        return make_run('new-run', 'SUCCEEDED')

    apify_client_async_patcher.patch(resource, 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('new-run', 'RUNNING'))
    apify_client_async_patcher.patch('run', 'wait_for_finish', replacement_method=wait_for_finish)
    apify_client_async_patcher.patch('run', 'get_status_message_watcher', return_value=MagicMock())
    apify_client_async_patcher.patch('run', 'get_streamed_log', replacement_method=get_streamed_log)

    async with Actor:
        calls = [getattr(Actor, method)('some-id', run_name='scrape-eu') for _ in range(3)]
        runs = await asyncio.gather(*calls)

    assert {run.status for run in runs} == {'SUCCEEDED'}
    assert len(apify_client_async_patcher.calls[resource]['start']) == 1
    assert get_streamed_log.call_count == 1


async def test_named_call_task_returns_aborted_run(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A named task call whose recorded run was aborted returns it without resurrecting it."""
    apify_client_async_patcher.patch('task', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', 'ABORTED'))
    apify_client_async_patcher.patch('run', 'resurrect', return_value=make_run('old-run', 'RUNNING'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run', actor_id=None, task_id='some-task')
        run = await Actor.call_task('some-task', run_name='scrape-eu', logger=None)

    assert run.id == 'old-run'
    assert run.status == 'ABORTED'
    assert apify_client_async_patcher.calls['task']['start'] == []
    assert apify_client_async_patcher.calls['run']['resurrect'] == []


async def test_named_call_task_rejects_name_recorded_for_actor(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """Reusing an Actor run's name for a task raises instead of attaching to the Actor's run."""
    apify_client_async_patcher.patch('task', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', 'RUNNING'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run')
        with pytest.raises(ValueError, match='already used for a different Actor, task, input or run options'):
            await Actor.call_task('some-task', run_name='scrape-eu', logger=None)

    assert apify_client_async_patcher.calls['task']['start'] == []


async def test_named_runs_forward_max_items_to_start(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """Named `start`, `call` and `call_task` pass `max_items` to the started run."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('task', 'start', return_value=make_run('new-task-run', 'READY'))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=make_run('new-run', 'SUCCEEDED'))

    async with Actor:
        await Actor.start('some-actor', run_name='started', max_items=10)
        await Actor.call('some-actor', run_name='called', max_items=20, logger=None)
        await Actor.call_task('some-task', run_name='task-called', max_items=30, logger=None)

    assert [kwargs['max_items'] for _, kwargs in apify_client_async_patcher.calls['actor']['start']] == [10, 20]
    [(_, task_kwargs)] = apify_client_async_patcher.calls['task']['start']
    assert task_kwargs['max_items'] == 30


async def test_named_start_warns_about_max_items_once(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A named start with `max_items` warns about the deprecated option once, pointing at the caller."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor:
        with pytest.warns(FutureWarning, match='max_items') as warnings:
            await Actor.start('some-actor', run_name='scrape-eu', max_items=10)

    future_warnings = [warning for warning in warnings if warning.category is FutureWarning]
    assert [warning.filename for warning in future_warnings] == [__file__]


async def test_named_start_task_records_run_in_kvs(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A named task start records the run under the task ID without waiting for it."""
    apify_client_async_patcher.patch('task', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor:
        run = await Actor.start_task('some-task', run_name='scrape-eu')
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert run.id == 'new-run'
    assert stored == stored_registry(
        {'scrape-eu': stored_record('new-run', 'READY', actor_id=None, task_id='some-task')}
    )
    assert apify_client_async_patcher.calls['run']['wait_for_finish'] == []


async def test_named_start_task_reuses_recorded_run(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A named task start returns the recorded running run without starting the task again."""
    apify_client_async_patcher.patch('task', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', 'RUNNING'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run', actor_id=None, task_id='some-task')
        run = await Actor.start_task('some-task', run_name='scrape-eu')

    assert run.id == 'old-run'
    assert apify_client_async_patcher.calls['task']['start'] == []


async def test_name_lock_is_dropped_after_named_start(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """The per-key lock is released from the registry once no named start holds it."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))

    async with _ActorType() as actor:
        await actor.start('some-actor', run_name='scrape-eu')
        assert len(actor._child_run_registry._key_locks) == 0


async def test_named_start_retries_recorded_run_not_found_yet(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """A recorded run the API briefly reports as missing is looked up again and reattached, not replaced."""
    get_run = Mock(side_effect=[None, make_run('old-run', 'RUNNING')])
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', replacement_method=get_run)

    async with Actor:
        await record_child_run('scrape-eu', 'old-run')
        run = await Actor.start('some-actor', run_name='scrape-eu')

    assert run.id == 'old-run'
    assert get_run.call_count == 2
    assert apify_client_async_patcher.calls['actor']['start'] == []


@pytest.mark.parametrize(
    'status',
    [
        pytest.param('RUNNING', id='running'),
        pytest.param('SUCCEEDED', id='succeeded'),
        pytest.param('FAILED', id='failed'),
        pytest.param('ABORTED', id='aborted'),
    ],
)
async def test_named_start_rejects_name_recorded_with_other_input(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
    status: str,
) -> None:
    """Reusing a name with a different input raises, whatever the status of the recorded run."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', status))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run', run_input={'since': '2025-01-01'})
        with pytest.raises(ValueError, match='already used for a different Actor, task, input or run options'):
            await Actor.start('some-actor', {'since': '2026-01-01'}, run_name='scrape-eu')

    assert apify_client_async_patcher.calls['actor']['start'] == []
    assert apify_client_async_patcher.calls['run']['get'] == []


@pytest.mark.parametrize(
    ('recorded_options', 'call_options'),
    [
        pytest.param({}, {'build': 'beta'}, id='option added'),
        pytest.param({'build': 'latest'}, {'build': 'beta'}, id='option changed'),
        pytest.param({'forcePermissionLevel': 'FULL_PERMISSIONS'}, {}, id='option removed'),
    ],
)
async def test_named_start_rejects_name_recorded_with_other_options(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
    recorded_options: dict[str, Any],
    call_options: dict[str, Any],
) -> None:
    """Reusing a name with different run options raises."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', 'RUNNING'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run', options=recorded_options)
        with pytest.raises(ValueError, match='already used for a different Actor, task, input or run options'):
            await Actor.start('some-actor', run_name='scrape-eu', **call_options)

    assert apify_client_async_patcher.calls['actor']['start'] == []


async def test_named_start_reuses_run_recorded_with_same_options(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """A call with the recorded checked run options returns the recorded run, whatever its other run options."""
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', 'SUCCEEDED'))
    recorded_options = {
        'build': 'beta',
        'forcePermissionLevel': 'LIMITED_PERMISSIONS',
        'webhooks': [{'eventTypes': ['ACTOR.RUN.SUCCEEDED'], 'requestUrl': 'https://example.com/hook'}],
    }

    async with Actor:
        await record_child_run('scrape-eu', 'old-run', options=recorded_options)
        run = await Actor.call(
            'some-actor',
            run_name='scrape-eu',
            build='beta',
            force_permission_level='LIMITED_PERMISSIONS',
            max_total_charge_usd=Decimal('1.50'),
            memory_mbytes=2048,
            restart_on_error=True,
            timeout=timedelta(seconds=90),
            webhooks=[Webhook(event_types=['ACTOR.RUN.SUCCEEDED'], request_url='https://example.com/hook')],
            token='other-token',
            wait=timedelta(seconds=5),
        )

    assert run.id == 'old-run'


async def test_named_start_ignores_input_key_order(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """An input equal to the recorded one up to key order reattaches to the recorded run."""
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', 'RUNNING'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run', run_input={'a': 1, 'nested': {'x': 1, 'y': 2}})
        run = await Actor.start('some-actor', {'nested': {'y': 2, 'x': 1}, 'a': 1}, run_name='scrape-eu')

    assert run.id == 'old-run'


@pytest.mark.parametrize(
    ('request_kwargs', 'expected'),
    [
        pytest.param(
            {
                'actor_id': 'some-actor',
                'task_id': None,
                'run_input': {
                    'urls': ['https://example.com'],
                    'maxPages': 10,
                    'nested': {'z': True, 'a': None},
                    'name': 'Žluťoučký',
                },
            },
            '79f4451cdbbc9bce11e153be41fe35ab3b0e64d1a0122cf7fafe897b6dfbab63',
            id='actor with input',
        ),
        pytest.param(
            {'actor_id': None, 'task_id': 'some-task', 'run_input': None},
            '141ee5857ab4cc98bc2cb9db49accebb94a84a44633abfc94a0ae2e80ad3c2cc',
            id='task without input',
        ),
    ],
)
def test_checksum_matches_js_sdk(request_kwargs: dict[str, Any], expected: str) -> None:
    """The request checksum equals the one the JS SDK computes for the same Actor or task and input."""
    assert checksum_request(**request_kwargs) == expected


def test_checksum_hashes_canonical_json_of_the_request() -> None:
    """The checksum is the SHA-256 of the request as canonical JSON, with sorted keys and no whitespace."""
    checksum = checksum_request(
        actor_id='some-actor',
        run_input={'b': [1.0, 2.5, 1e21, 1e-7], 'a': '\u00e9"\n'},
        options={'timeout': 60, 'memory': 256},
    )
    canonical = (
        '{"id":"some-actor","input":{"a":"\u00e9\\"\\n","b":[1,2.5,1e+21,1e-7]},'
        '"options":{"memory":256,"timeout":60},"type":"actor"}'
    )

    assert checksum == hashlib.sha256(canonical.encode()).hexdigest()


@pytest.mark.parametrize(
    ('run_input', 'canonical_input'),
    [
        pytest.param({'n': 0.0}, '{"n":0}', id='zero'),
        pytest.param({'n': -0.5}, '{"n":-0.5}', id='negative fraction'),
        pytest.param({'n': 0.001}, '{"n":0.001}', id='small fraction'),
        pytest.param({'n': -12}, '{"n":-12}', id='negative integer'),
        pytest.param({'on': False, 'off': None}, '{"off":null,"on":false}', id='false and null'),
        pytest.param(
            {'\ufb33': 1, '\U0001f600': 2}, '{"\U0001f600":2,"\ufb33":1}', id='keys sorted by UTF-16 code units'
        ),
    ],
)
def test_checksum_serializes_json_values_canonically(run_input: Any, canonical_input: str) -> None:
    """The checksum writes numbers, literals and object keys the way RFC 8785 defines."""
    canonical = f'{{"id":"some-actor","input":{canonical_input},"type":"actor"}}'

    assert (
        checksum_request(actor_id='some-actor', run_input=run_input) == hashlib.sha256(canonical.encode()).hexdigest()
    )


def test_checksum_accepts_an_empty_content_type() -> None:
    """An empty content type counts as not set, the same as in the client."""
    assert checksum_request(actor_id='some-actor', run_input={'a': 1}, content_type='') == checksum_request(
        actor_id='some-actor', run_input={'a': 1}
    )


@pytest.mark.parametrize(
    ('first_input', 'second_input'),
    [
        pytest.param({'count': 1}, {'count': 1.0}, id='integer and equal float'),
        pytest.param({'a': 1, 'b': 2}, {'b': 2, 'a': 1}, id='key order'),
        pytest.param({'price': Decimal('1.50')}, {'price': '1.50'}, id='value the client sends as a string'),
    ],
)
def test_checksum_is_equal_for_inputs_sent_as_the_same_json(first_input: Any, second_input: Any) -> None:
    """Two inputs that the client sends as the same JSON document have the same checksum."""
    first = checksum_request(actor_id='some-actor', run_input=first_input)
    second = checksum_request(actor_id='some-actor', run_input=second_input)

    assert first == second


def test_checksum_differs_for_actor_and_task_with_the_same_id() -> None:
    """An Actor and a task with the same ID have different checksums."""
    assert checksum_request(actor_id='some-id') != checksum_request(task_id='some-id')


def test_checksum_ignores_json_content_type_and_empty_options() -> None:
    """A JSON content type and no run options leave the checksum as it is without them."""
    plain = checksum_request(actor_id='some-actor', run_input={'a': 1})
    with_content_type = checksum_request(
        actor_id='some-actor', run_input={'a': 1}, content_type='application/json; charset=utf-8', options={}
    )

    assert plain == with_content_type


@pytest.mark.parametrize(
    ('run_input', 'content_type'),
    [
        pytest.param('{"a": 1}', None, id='string'),
        pytest.param(b'{"a": 1}', None, id='bytes'),
        pytest.param(io.BytesIO(b'{"a": 1}'), None, id='stream'),
        pytest.param({'a': 1}, 'text/plain', id='other content type'),
    ],
)
def test_checksum_leaves_out_input_not_sent_as_json(
    run_input: Any, content_type: str | None, caplog: pytest.LogCaptureFixture
) -> None:
    """An input that the client does not serialize to JSON is left out of the checksum, with a warning."""
    checksum = checksum_request(
        actor_id='some-actor', run_input=run_input, content_type=content_type, run_name='scrape-eu'
    )

    assert checksum == checksum_request(actor_id='some-actor')
    assert 'The input of child run "scrape-eu" is not JSON' in caplog.text


def test_checksum_run_options_use_the_api_names_and_values() -> None:
    """The hashed run options carry the names and values of the API, and the options that are not set are left out."""
    options = checksum_run_options(
        build='beta',
        force_permission_level='FULL_PERMISSIONS',
        webhooks=to_client_representations(
            [Webhook(event_types=['ACTOR.RUN.FAILED'], request_url='https://example.com/hook')]
        ),
    )

    assert options == {
        'build': 'beta',
        'forcePermissionLevel': 'FULL_PERMISSIONS',
        'webhooks': [{'eventTypes': ['ACTOR.RUN.FAILED'], 'requestUrl': 'https://example.com/hook'}],
    }
    assert checksum_run_options() == {}


async def test_named_start_returns_recorded_run_for_input_not_sent_as_json(
    apify_client_async_patcher: ApifyClientAsyncPatcher, caplog: pytest.LogCaptureFixture
) -> None:
    """A named start with an input that is not sent as JSON returns the recorded run without checking the input."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', 'RUNNING'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run')
        run = await Actor.start('some-actor', 'plain text', run_name='scrape-eu')

    assert run.id == 'old-run'
    assert apify_client_async_patcher.calls['actor']['start'] == []
    assert 'was not checked against the recorded run' in caplog.text


async def test_reattached_run_status_is_recorded(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """Reattaching to a recorded run stores its current status."""
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', 'SUCCEEDED'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run')
        await Actor.start('some-actor', run_name='scrape-eu')
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert stored == stored_registry({'scrape-eu': stored_record('old-run', 'SUCCEEDED')})


async def test_named_call_records_finished_status(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A named call stores the status of the run once it finishes."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=make_run('new-run', 'FAILED'))

    async with Actor:
        await Actor.call('some-actor', run_name='scrape-eu', logger=None)
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert stored == stored_registry({'scrape-eu': stored_record('new-run', 'FAILED')})


async def test_child_runs_is_empty_without_child_runs() -> None:
    """`Actor.child_runs` is empty when no child run was started."""
    async with Actor:
        assert Actor.child_runs == []


def test_child_runs_requires_initialized_actor() -> None:
    """`Actor.child_runs` raises outside of the Actor context."""
    with pytest.raises(RuntimeError, match='not active'):
        _ = Actor.child_runs


async def test_child_runs_includes_runs_recorded_before_init() -> None:
    """Init loads the runs recorded by an earlier process, so `Actor.child_runs` has an entry for each of them."""
    async with Actor:
        kvs = await Actor.open_key_value_store()
        await kvs.set_value(
            CHILD_RUNS_KEY,
            stored_registry(
                {
                    'scrape-eu': stored_record('eu-run', 'RUNNING'),
                    'scrape-us': stored_record('us-run', 'FAILED', actor_id=None, task_id='some-task'),
                },
                runs={'run:other-run': {'runId': 'other-run', 'status': 'SUCCEEDED', 'abortWithParent': False}},
            ),
        )

    async with Actor:
        child_runs = Actor.child_runs

    assert {name: child_run.client.resource_id for name, child_run in named_child_runs(child_runs).items()} == {
        'scrape-eu': 'eu-run',
        'scrape-us': 'us-run',
    }
    assert named_child_runs(child_runs)['scrape-us'].record.status == 'FAILED'
    assert [child_run.key for child_run in child_runs] == ['name:scrape-eu', 'name:scrape-us', 'run:other-run']


async def test_child_runs_includes_run_started_in_this_process(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """A run started by a named start shows up in `Actor.child_runs` right away, with its record and a client."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor:
        await Actor.start('some-actor', run_name='scrape-eu', abort_with_parent=True)
        child_runs = Actor.child_runs

    assert named_child_runs(child_runs).keys() == {'scrape-eu'}
    key, record, client = named_child_runs(child_runs)['scrape-eu']
    assert key == 'name:scrape-eu'
    assert client.resource_id == 'new-run'
    assert record == ChildRunRecord(
        run_id='new-run',
        status='READY',
        checksum=checksum_request(actor_id='some-actor'),
        abort_with_parent=True,
    )


async def test_child_runs_record_is_read_only(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """The record of a child run cannot be changed, so the registry keeps its values."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor:
        await Actor.start('some-actor', run_name='scrape-eu')
        record = named_child_runs(Actor.child_runs)['scrape-eu'].record
        with pytest.raises(ValidationError, match='frozen'):
            record.status = 'SUCCEEDED'  # ty: ignore[invalid-assignment]
        assert named_child_runs(Actor.child_runs)['scrape-eu'].record.status == 'READY'


async def test_child_runs_uses_client_of_named_start(
    apify_client_async_patcher: ApifyClientAsyncPatcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run started with a custom token gets a client with that token, a run recorded earlier the default one."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('custom-run', 'READY'))
    new_client = _ActorType.new_client
    clients_by_token: dict[str | None, ApifyClientAsync] = {}

    def recording_new_client(self: _ActorType, **kwargs: Any) -> ApifyClientAsync:
        client = new_client(self, **kwargs)
        clients_by_token[kwargs.get('token')] = client
        return client

    monkeypatch.setattr(_ActorType, 'new_client', recording_new_client)

    async with Actor:
        await record_child_run('recorded', 'recorded-run')
        await Actor.start('some-actor', run_name='custom', token='custom-token')
        child_runs = Actor.child_runs
        default_http_client = Actor.apify_client._http_client

    custom_http_client = clients_by_token['custom-token']._http_client
    assert custom_http_client is not default_http_client
    assert named_child_runs(child_runs)['custom'].client._http_client is custom_http_client
    assert named_child_runs(child_runs)['recorded'].client._http_client is default_http_client


async def test_child_runs_keeps_client_of_name_after_rejected_reuse(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """A name reuse rejected for a different input leaves `Actor.child_runs` with the original client."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('new-run', 'RUNNING'))

    async with Actor:
        await Actor.start('some-actor', {'since': '2025-01-01'}, run_name='scrape-eu')
        with pytest.raises(ValueError, match='already used for a different Actor, task, input or run options'):
            await Actor.start('some-actor', {'since': '2026-01-01'}, run_name='scrape-eu', token='other-token')
        child_runs = Actor.child_runs
        default_http_client = Actor.apify_client._http_client

    assert named_child_runs(child_runs)['scrape-eu'].client._http_client is default_http_client


async def test_child_runs_keeps_client_of_name_after_failed_lookup(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """A named start whose lookup of the recorded run fails leaves `Actor.child_runs` with the original client."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', replacement_method=Mock(side_effect=RuntimeError('forbidden')))

    async with Actor:
        await Actor.start('some-actor', run_name='scrape-eu')
        with pytest.raises(RuntimeError, match='forbidden'):
            await Actor.start('some-actor', run_name='scrape-eu', token='other-token')
        child_runs = Actor.child_runs
        default_http_client = Actor.apify_client._http_client

    assert named_child_runs(child_runs)['scrape-eu'].client._http_client is default_http_client


@pytest.mark.parametrize(
    'method',
    [
        pytest.param('start', id='start'),
        pytest.param('call', id='call'),
        pytest.param('start_task', id='start task'),
        pytest.param('call_task', id='call task'),
    ],
)
async def test_abort_with_parent_requires_run_name(
    apify_client_async_patcher: ApifyClientAsyncPatcher, method: str
) -> None:
    """`abort_with_parent` without a `run_name` raises before any run is started."""
    for resource in ('actor', 'task'):
        apify_client_async_patcher.patch(resource, 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('actor', 'call', return_value=make_run('new-run', 'SUCCEEDED'))

    async with Actor:
        with pytest.raises(ValueError, match='requires `run_name`'):
            await getattr(Actor, method)('some-id', abort_with_parent=True)

    for resource in ('actor', 'task'):
        assert apify_client_async_patcher.calls[resource]['start'] == []
    assert apify_client_async_patcher.calls['actor']['call'] == []


async def test_named_start_records_abort_with_parent(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A named start with `abort_with_parent` records the flag with the run."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor:
        await Actor.start('some-actor', run_name='scrape-eu', abort_with_parent=True)
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert stored['runs']['name:scrape-eu']['abortWithParent'] is True


async def test_named_call_task_records_abort_with_parent(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """A named task call with `abort_with_parent` records the flag with the run."""
    apify_client_async_patcher.patch('task', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=make_run('new-run', 'SUCCEEDED'))

    async with Actor:
        await Actor.call_task('some-task', run_name='scrape-eu', abort_with_parent=True, logger=None)
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert stored['runs']['name:scrape-eu']['abortWithParent'] is True


async def test_reattach_replaces_recorded_abort_with_parent(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """Reattaching under a name records the `abort_with_parent` value of the latest call."""
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', 'RUNNING'))

    async with Actor:
        await record_child_run('scrape-eu', 'old-run')
        await Actor.start('some-actor', run_name='scrape-eu', abort_with_parent=True)
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert stored['runs']['name:scrape-eu']['runId'] == 'old-run'
    assert stored['runs']['name:scrape-eu']['abortWithParent'] is True


async def test_aborting_event_aborts_marked_child_runs(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
    caplog: pytest.LogCaptureFixture,
    apify_event_manager: ApifyEventManager,
) -> None:
    """On `ABORTING`, each child run marked `abort_with_parent` gets one graceful abort request and no status lookup."""
    aborted_runs = {
        'running-run': make_run('running-run', 'ABORTING'),
        'ready-run': make_run('ready-run', 'ABORTED'),
        'finished-run': make_run('finished-run', 'SUCCEEDED'),
    }

    async def abort_run(run_client: Any, *_args: Any, **_kwargs: Any) -> Run:
        return aborted_runs[run_client.resource_id]

    apify_client_async_patcher.patch('run', 'get', return_value=None)
    apify_client_async_patcher.patch('run', 'abort', replacement_method=abort_run)
    caplog.set_level('INFO')

    async with Actor:
        kvs = await Actor.open_key_value_store()
        records = {
            name: stored_record(run_id, 'RUNNING', abort_with_parent=marked)
            for name, run_id, marked in [
                ('running', 'running-run', True),
                ('ready', 'ready-run', True),
                ('finished', 'finished-run', True),
                ('unmarked', 'unmarked-run', False),
            ]
        }
        await kvs.set_value(CHILD_RUNS_KEY, stored_registry(records))
        await Actor._child_run_registry.load()
        apify_event_manager.emit(event=Event.ABORTING, event_data=EventAbortingData())
        await apify_event_manager.wait_for_all_listeners_to_complete()

    aborts = apify_client_async_patcher.calls['run']['abort']
    assert sorted(args[0].resource_id for args, _ in aborts) == ['finished-run', 'ready-run', 'running-run']
    assert all(kwargs == {'gracefully': True} for _, kwargs in aborts)
    assert apify_client_async_patcher.calls['run']['get'] == []
    assert 'Aborted child run "name:running" with the parent' in caplog.text
    assert 'Aborted child run "name:ready" with the parent' in caplog.text
    assert 'Aborted child run "finished"' not in caplog.text


async def test_aborting_event_skips_a_child_run_that_no_longer_exists(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
    caplog: pytest.LogCaptureFixture,
    apify_event_manager: ApifyEventManager,
) -> None:
    """A marked child run the API no longer knows is not reported as a failed abort."""
    not_found = NotFoundError(Mock(status_code=404, json=Mock(return_value={})), 1, method='POST')
    apify_client_async_patcher.patch('run', 'abort', replacement_method=Mock(side_effect=not_found))

    async with Actor:
        kvs = await Actor.open_key_value_store()
        record = stored_record('gone-run', 'RUNNING', abort_with_parent=True)
        await kvs.set_value(CHILD_RUNS_KEY, stored_registry({'gone': record}))
        await Actor._child_run_registry.load()
        apify_event_manager.emit(event=Event.ABORTING, event_data=EventAbortingData())
        await apify_event_manager.wait_for_all_listeners_to_complete()

    assert len(apify_client_async_patcher.calls['run']['abort']) == 1
    assert 'Failed to abort child run' not in caplog.text


async def test_failed_child_run_abort_does_not_stop_others(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
    caplog: pytest.LogCaptureFixture,
    apify_event_manager: ApifyEventManager,
) -> None:
    """A child run that fails to abort is logged, and the other marked child runs are still aborted."""

    async def abort_run(run_client: Any, *_args: Any, **_kwargs: Any) -> Run:
        if run_client.resource_id == 'broken-run':
            raise RuntimeError('abort failed')
        return make_run(run_client.resource_id, 'ABORTING')

    apify_client_async_patcher.patch('run', 'abort', replacement_method=abort_run)

    async with Actor:
        kvs = await Actor.open_key_value_store()
        records = {
            name: stored_record(f'{name}-run', 'RUNNING', abort_with_parent=True) for name in ['broken', 'healthy']
        }
        await kvs.set_value(CHILD_RUNS_KEY, stored_registry(records))
        await Actor._child_run_registry.load()
        apify_event_manager.emit(event=Event.ABORTING, event_data=EventAbortingData())
        await apify_event_manager.wait_for_all_listeners_to_complete()

    aborts = apify_client_async_patcher.calls['run']['abort']
    assert sorted(args[0].resource_id for args, _ in aborts) == ['broken-run', 'healthy-run']
    assert 'Failed to abort child run "name:broken"' in caplog.text
    assert 'Aborted child run "name:healthy" with the parent' in caplog.text


async def test_child_run_is_aborted_with_the_client_it_was_started_with() -> None:
    """A child run started with its own client is aborted with that client, not the default one."""
    default_client = Mock()
    child_client = Mock()
    child_client.run.return_value.abort = AsyncMock(return_value=make_run('new-run', 'ABORTING'))

    async with Actor:
        registry = ChildRunRegistry(KeyValueStoreChildRunTracker(Actor.open_key_value_store))
        await registry.load()
        await registry.find_or_start(
            name_key('scrape-eu'),
            checksum='checksum',
            client=child_client,
            start_run=AsyncMock(return_value=make_run('new-run', 'READY')),
            abort_with_parent=True,
        )
        await registry.abort_runs_with_parent(default_client)

    child_client.run.return_value.abort.assert_awaited_once_with(gracefully=True)
    default_client.run.assert_not_called()


async def test_rejected_named_start_keeps_the_client_used_to_abort() -> None:
    """A named start rejected for another Actor does not change the client its recorded run is aborted with."""
    default_client = Mock()
    default_client.run.return_value.abort = AsyncMock(return_value=make_run('old-run', 'ABORTING'))
    other_client = Mock()
    other_client.run.return_value.get = AsyncMock(return_value=make_run('old-run', 'RUNNING'))
    other_client.run.return_value.abort = AsyncMock()

    async with Actor:
        kvs = await Actor.open_key_value_store()
        record = stored_record('old-run', 'RUNNING', abort_with_parent=True)
        await kvs.set_value(CHILD_RUNS_KEY, stored_registry({'scrape-eu': record}))
        registry = ChildRunRegistry(KeyValueStoreChildRunTracker(Actor.open_key_value_store))
        await registry.load()
        with pytest.raises(ValueError, match='already used for a different Actor, task, input or run options'):
            await registry.find_or_start(
                name_key('scrape-eu'),
                checksum='other-checksum',
                client=other_client,
                start_run=AsyncMock(),
            )
        await registry.abort_runs_with_parent(default_client)

    default_client.run.return_value.abort.assert_awaited_once_with(gracefully=True)
    other_client.run.return_value.abort.assert_not_awaited()


async def test_aborting_waits_for_a_named_start_in_flight() -> None:
    """A named start in flight when the parent is aborted has its run aborted once the run is recorded."""
    client = Mock()
    client.run.return_value.abort = AsyncMock(return_value=make_run('new-run', 'ABORTING'))
    started = asyncio.Event()
    release = asyncio.Event()

    async def start_run() -> Run:
        started.set()
        await release.wait()
        return make_run('new-run', 'READY')

    async with Actor:
        registry = ChildRunRegistry(KeyValueStoreChildRunTracker(Actor.open_key_value_store))
        await registry.load()
        start_task = asyncio.create_task(
            registry.find_or_start(
                name_key('scrape-eu'),
                checksum='checksum',
                client=client,
                start_run=start_run,
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


async def test_named_start_queued_behind_a_start_in_flight_raises_once_aborting() -> None:
    """A named start waiting on its name while the parent is aborted raises, and the run in flight is aborted."""
    client = Mock()
    client.run.return_value.abort = AsyncMock(return_value=make_run('new-run', 'ABORTING'))
    started = asyncio.Event()
    release = asyncio.Event()

    async def start_run() -> Run:
        started.set()
        await release.wait()
        return make_run('new-run', 'READY')

    queued_start_run = AsyncMock()

    async with Actor:
        registry = ChildRunRegistry(KeyValueStoreChildRunTracker(Actor.open_key_value_store))
        await registry.load()
        key = name_key('scrape-eu')
        options: dict[str, Any] = {'checksum': 'checksum', 'client': client, 'abort_with_parent': True}
        first_start = asyncio.create_task(registry.find_or_start(key, start_run=start_run, **options))
        await started.wait()
        queued_start = asyncio.create_task(registry.find_or_start(key, start_run=queued_start_run, **options))
        await asyncio.sleep(0)
        abort_task = asyncio.create_task(registry.abort_runs_with_parent(client))
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(first_start, abort_task)
        with pytest.raises(RuntimeError, match='being aborted'):
            await queued_start

    queued_start_run.assert_not_awaited()
    client.run.return_value.abort.assert_awaited_once_with(gracefully=True)


@pytest.mark.parametrize(
    ('method', 'resource'),
    [
        pytest.param('start', 'actor', id='start'),
        pytest.param('call', 'actor', id='call'),
        pytest.param('start_task', 'task', id='start task'),
        pytest.param('call_task', 'task', id='call task'),
    ],
)
async def test_named_start_with_abort_with_parent_raises_once_aborting(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
    apify_event_manager: ApifyEventManager,
    method: str,
    resource: str,
) -> None:
    """After `ABORTING`, a new named start with `abort_with_parent` raises and starts no run."""
    apify_client_async_patcher.patch(resource, 'start', return_value=make_run('new-run', 'READY'))

    async with Actor:
        apify_event_manager.emit(event=Event.ABORTING, event_data=EventAbortingData())
        await apify_event_manager.wait_for_all_listeners_to_complete()
        with pytest.raises(RuntimeError, match='being aborted'):
            await getattr(Actor, method)('some-id', run_name='scrape-eu', abort_with_parent=True)
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert apify_client_async_patcher.calls[resource]['start'] == []
    assert stored is None


async def test_named_call_once_aborting_does_not_resurrect_the_aborted_child(
    apify_client_async_patcher: ApifyClientAsyncPatcher, apify_event_manager: ApifyEventManager
) -> None:
    """After `ABORTING`, a named call with `abort_with_parent` under a recorded name leaves the aborted child alone."""
    apify_client_async_patcher.patch('run', 'abort', return_value=make_run('old-run', 'ABORTING'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', 'ABORTED'))
    apify_client_async_patcher.patch('run', 'resurrect', return_value=make_run('old-run', 'RUNNING'))

    async with Actor:
        kvs = await Actor.open_key_value_store()
        record = stored_record('old-run', 'RUNNING', abort_with_parent=True)
        await kvs.set_value(CHILD_RUNS_KEY, stored_registry({'scrape-eu': record}))
        await Actor._child_run_registry.load()
        apify_event_manager.emit(event=Event.ABORTING, event_data=EventAbortingData())
        await apify_event_manager.wait_for_all_listeners_to_complete()
        with pytest.raises(RuntimeError, match='being aborted'):
            await Actor.call('some-actor', run_name='scrape-eu', abort_with_parent=True)

    assert len(apify_client_async_patcher.calls['run']['abort']) == 1
    assert apify_client_async_patcher.calls['run']['resurrect'] == []
    assert apify_client_async_patcher.calls['actor']['start'] == []


async def test_named_start_without_abort_with_parent_is_not_blocked_once_aborting(
    apify_client_async_patcher: ApifyClientAsyncPatcher, apify_event_manager: ApifyEventManager
) -> None:
    """After `ABORTING`, a named start without `abort_with_parent` still starts its run."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor:
        apify_event_manager.emit(event=Event.ABORTING, event_data=EventAbortingData())
        await apify_event_manager.wait_for_all_listeners_to_complete()
        run = await Actor.start('some-actor', run_name='scrape-eu')

    assert run.id == 'new-run'


async def test_exit_removes_the_aborting_listener(
    apify_client_async_patcher: ApifyClientAsyncPatcher, apify_event_manager: ApifyEventManager
) -> None:
    """After the Actor exits, an `ABORTING` event on a still-active event manager aborts no child run."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'abort', return_value=make_run('new-run', 'ABORTING'))

    async with apify_event_manager:
        async with Actor:
            await Actor.start('some-actor', run_name='scrape-eu', abort_with_parent=True)
        apify_event_manager.emit(event=Event.ABORTING, event_data=EventAbortingData())
        await apify_event_manager.wait_for_all_listeners_to_complete()

    assert apify_client_async_patcher.calls['run']['abort'] == []


async def test_removing_all_aborting_listeners_keeps_aborting_child_runs(
    apify_client_async_patcher: ApifyClientAsyncPatcher, apify_event_manager: ApifyEventManager
) -> None:
    """Removing all `ABORTING` listeners from the event manager still aborts child runs marked `abort_with_parent`."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'abort', return_value=make_run('new-run', 'ABORTING'))

    async with Actor:
        await Actor.start('some-actor', run_name='scrape-eu', abort_with_parent=True)
        apify_event_manager.off(event=Event.ABORTING)
        apify_event_manager.emit(event=Event.ABORTING, event_data=EventAbortingData())
        await apify_event_manager.wait_for_all_listeners_to_complete()

    assert len(apify_client_async_patcher.calls['run']['abort']) == 1


@pytest.mark.parametrize(
    'method_name',
    [
        pytest.param('start', id='start'),
        pytest.param('call', id='call'),
        pytest.param('start_task', id='start task'),
        pytest.param('call_task', id='call task'),
    ],
)
async def test_named_run_warns_experimental(
    apify_client_async_patcher: ApifyClientAsyncPatcher, method_name: str
) -> None:
    """A run started with `run_name` warns that named child runs are experimental, pointing at the caller."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('task', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=make_run('new-run', 'SUCCEEDED'))

    async with Actor:
        method = getattr(Actor, method_name)
        target = 'some-task' if method_name.endswith('_task') else 'some-actor'
        kwargs = {'logger': None} if method_name in {'call', 'call_task'} else {}
        with pytest.warns(UserWarning, match='experimental') as warnings:
            await method(target, run_name='scrape-eu', **kwargs)

    # Only the user warnings count: a `ResourceWarning` from an object of an earlier test can be collected here.
    assert [warning.filename for warning in warnings if issubclass(warning.category, UserWarning)] == [__file__]


async def test_unnamed_start_does_not_warn_experimental(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A run started without `run_name` emits no experimental warning."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor:
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            await Actor.start('some-actor')


async def test_child_runs_warns_experimental() -> None:
    """Accessing `Actor.child_runs` warns that named child runs are experimental, pointing at the caller."""
    async with Actor:
        with pytest.warns(UserWarning, match='experimental') as warnings:
            _ = Actor.child_runs

    # Only the user warnings count: a `ResourceWarning` from an object of an earlier test can be collected here.
    assert [warning.filename for warning in warnings if issubclass(warning.category, UserWarning)] == [__file__]


async def test_aborting_event_before_the_registry_is_loaded_waits_for_it() -> None:
    """An abort of the child runs that starts before the registry is loaded aborts the recorded runs after the load."""
    client = Mock()
    client.run.return_value.abort = AsyncMock(return_value=make_run('old-run', 'ABORTING'))

    async with Actor:
        kvs = await Actor.open_key_value_store()
        record = stored_record('old-run', 'RUNNING', abort_with_parent=True)
        await kvs.set_value(CHILD_RUNS_KEY, stored_registry({'scrape-eu': record}))
        registry = ChildRunRegistry(KeyValueStoreChildRunTracker(Actor.open_key_value_store))
        abort_task = asyncio.create_task(registry.abort_runs_with_parent(client))
        await asyncio.sleep(0.05)
        assert not abort_task.done()
        await registry.load()
        await asyncio.wait_for(abort_task, timeout=1)

    client.run.return_value.abort.assert_awaited_once_with(gracefully=True)


@pytest.mark.parametrize(
    'stored',
    [
        pytest.param([], id='empty list'),
        pytest.param('', id='empty string'),
        pytest.param(0, id='zero'),
    ],
)
async def test_init_rejects_registry_of_another_json_type(stored: Any) -> None:
    """Init raises a `ValueError` for a registry value that is not a JSON object, also when the value is falsy."""
    async with Actor:
        kvs = await Actor.open_key_value_store()
        await kvs.set_value(CHILD_RUNS_KEY, stored)

    with pytest.raises(ValueError, match=CHILD_RUNS_KEY):
        await Actor.init()


async def test_failed_load_releases_an_abort_of_child_runs_that_waits_for_it() -> None:
    """An abort of the child runs that waits for the registry returns when the load fails, and aborts nothing."""
    client = Mock()
    client.run.return_value.abort = AsyncMock()

    async with Actor:
        kvs = await Actor.open_key_value_store()
        await kvs.set_value(CHILD_RUNS_KEY, stored_registry({'scrape-eu': {'runId': 'old-run'}}))
        registry = ChildRunRegistry(KeyValueStoreChildRunTracker(Actor.open_key_value_store))
        abort_task = asyncio.create_task(registry.abort_runs_with_parent(client))
        await asyncio.sleep(0)
        with pytest.raises(ValueError, match=CHILD_RUNS_KEY):
            await registry.load()
        await asyncio.wait_for(abort_task, timeout=1)

    client.run.return_value.abort.assert_not_awaited()


async def test_abort_of_child_runs_stops_waiting_for_a_load_that_never_happens() -> None:
    """An abort of the child runs that waits for the registry returns when the Actor gives up loading it."""
    client = Mock()

    async with Actor:
        registry = ChildRunRegistry(KeyValueStoreChildRunTracker(Actor.open_key_value_store))
        abort_task = asyncio.create_task(registry.abort_runs_with_parent(client))
        await asyncio.sleep(0)
        registry.stop_waiting_for_load()
        await asyncio.wait_for(abort_task, timeout=1)

    client.run.assert_not_called()


async def test_tracking_off_starts_runs_without_recording_them(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """With `child_run_tracker=None`, a start neither reads nor writes the registry."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor(child_run_tracker=None):
        run = await Actor.start('some-actor')
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert run.id == 'new-run'
    assert stored is None


@pytest.mark.parametrize(
    'kwargs',
    [
        pytest.param({'run_name': 'scrape-eu'}, id='run name'),
        pytest.param({'run_name': 'scrape-eu', 'abort_with_parent': True}, id='abort with parent'),
    ],
)
async def test_tracking_off_rejects_child_run_options(
    apify_client_async_patcher: ApifyClientAsyncPatcher, kwargs: dict[str, Any]
) -> None:
    """With child run tracking off, `run_name` and `abort_with_parent` raise a `ValueError` and start no run."""
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor(child_run_tracker=None):
        with pytest.raises(ValueError, match='child run tracking'):
            await Actor.start('some-actor', **kwargs)

    assert apify_client_async_patcher.calls['actor']['start'] == []


async def test_tracking_off_child_runs_raises() -> None:
    """With child run tracking off, `Actor.child_runs` raises a `RuntimeError`."""
    async with Actor(child_run_tracker=None):
        with pytest.raises(RuntimeError, match='child run tracking is turned off'):
            _ = Actor.child_runs


async def test_custom_tracker_stores_and_lists_records(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    """A custom tracker gets every record to store, and its listed records are the ones `Actor.child_runs` shows."""
    recorded = ChildRunRecord(run_id='old-run', status='SUCCEEDED')
    tracker = AsyncMock(spec=ChildRunTracker)
    tracker.list_runs.return_value = {'run:old-run': recorded}
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor(child_run_tracker=tracker):
        await Actor.start('some-actor')
        keys = [child_run.key for child_run in Actor.child_runs]
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert keys == ['run:old-run', 'run:new-run']
    tracker.store_run.assert_awaited_once_with('run:new-run', ChildRunRecord(run_id='new-run', status='READY'))
    assert stored is None


@pytest.mark.parametrize(
    ('disable_warning', 'expected_warnings'),
    [
        pytest.param(False, 1, id='warning on'),
        pytest.param(True, 0, id='warning muted'),
    ],
)
async def test_excessive_child_runs_warning(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    *,
    disable_warning: bool,
    expected_warnings: int,
) -> None:
    """Once the registry holds more records than the threshold, one warning is logged, unless it is muted."""
    monkeypatch.setattr(_child_runs, 'EXCESSIVE_CHILD_RUNS_THRESHOLD', 2)
    runs = iter([make_run(f'run-{index}', 'READY') for index in range(4)])
    apify_client_async_patcher.patch('actor', 'start', replacement_method=lambda *_args, **_kwargs: next(runs))

    async with Actor(disable_excessive_child_run_warning=disable_warning):
        for _ in range(4):
            await Actor.start('some-actor')

    assert caplog.text.count('Too many child runs (3)') == expected_warnings
    assert 'Too many child runs (4)' not in caplog.text


async def test_registry_keeps_unknown_kinds_fields_and_members(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    """Records of unknown kinds, unknown record fields and unknown top-level members survive a rewrite."""
    unknown_record = {'runId': 'other-run', 'status': 'RUNNING', 'abortWithParent': False, 'extra': 1}
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor:
        kvs = await Actor.open_key_value_store()
        await kvs.set_value(CHILD_RUNS_KEY, {'runs': {'future:x': unknown_record}, 'version': 2})

    async with Actor:
        keys = [child_run.key for child_run in Actor.child_runs]
        await Actor.start('some-actor')
        kvs = await Actor.open_key_value_store()
        stored = await kvs.get_value(CHILD_RUNS_KEY)

    assert keys == ['future:x']
    assert stored == {
        'runs': {
            'future:x': unknown_record,
            'run:new-run': {'runId': 'new-run', 'status': 'READY', 'abortWithParent': False},
        },
        'version': 2,
    }


async def test_implicit_run_name_returns_run_of_identical_call(
    apify_client_async_patcher: ApifyClientAsyncPatcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With `auto_memoize_child_runs`, an identical call without a name returns the run recorded for the first one."""
    monkeypatch.setenv('APIFY_AUTO_MEMOIZE_CHILD_RUNS', 'true')
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('new-run', 'RUNNING'))

    async with Actor:
        first = await Actor.start('some-actor', {'q': 1}, build='beta')
        second = await Actor.start('some-actor', {'q': 1}, build='beta', memory_mbytes=2048)
        keys = [child_run.key for child_run in Actor.child_runs]

    checksum = checksum_request(actor_id='some-actor', run_input={'q': 1}, options={'build': 'beta'})
    assert first.id == second.id == 'new-run'
    assert len(apify_client_async_patcher.calls['actor']['start']) == 1
    assert keys == [f'implicit:{checksum}']


@pytest.mark.parametrize(
    'second_call',
    [
        pytest.param({'run_input': {'q': 2}}, id='different input'),
        pytest.param({'run_input': {'q': 1}, 'build': 'beta'}, id='different build'),
        pytest.param({'run_input': {'q': 1}, 'run_name': 'second'}, id='explicit run name'),
    ],
)
async def test_implicit_run_name_starts_new_run_for_different_call(
    apify_client_async_patcher: ApifyClientAsyncPatcher, monkeypatch: pytest.MonkeyPatch, second_call: dict[str, Any]
) -> None:
    """With `auto_memoize_child_runs`, a call with another request or with an explicit run name starts a new run."""
    monkeypatch.setenv('APIFY_AUTO_MEMOIZE_CHILD_RUNS', 'true')
    runs = iter([make_run('first-run', 'READY'), make_run('second-run', 'READY')])
    apify_client_async_patcher.patch('actor', 'start', replacement_method=lambda *_args, **_kwargs: next(runs))

    async with Actor:
        first = await Actor.start('some-actor', {'q': 1})
        second = await Actor.start('some-actor', **second_call)

    assert (first.id, second.id) == ('first-run', 'second-run')


async def test_implicit_run_name_rejects_input_not_sent_as_json(
    apify_client_async_patcher: ApifyClientAsyncPatcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With `auto_memoize_child_runs`, a call without a name and with an input that is not JSON raises a `TypeError`."""
    monkeypatch.setenv('APIFY_AUTO_MEMOIZE_CHILD_RUNS', 'true')
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))

    async with Actor:
        with pytest.raises(TypeError, match='implicit run name needs a JSON input'):
            await Actor.start('some-actor', 'plain text')

    assert apify_client_async_patcher.calls['actor']['start'] == []


async def test_implicit_run_name_resolves_run_recorded_by_earlier_process(
    apify_client_async_patcher: ApifyClientAsyncPatcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run recorded under an implicit run name by an earlier process is returned by an identical call."""
    monkeypatch.setenv('APIFY_AUTO_MEMOIZE_CHILD_RUNS', 'true')
    checksum = checksum_request(actor_id='some-actor', run_input={'q': 1})
    record = {'runId': 'old-run', 'status': 'RUNNING', 'abortWithParent': False, 'checksum': checksum}
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('new-run', 'READY'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('old-run', 'SUCCEEDED'))

    async with Actor:
        kvs = await Actor.open_key_value_store()
        await kvs.set_value(CHILD_RUNS_KEY, stored_registry(runs={f'implicit:{checksum}': record}))

    async with Actor:
        run = await Actor.start('some-actor', {'q': 1})

    assert run.id == 'old-run'
    assert run.status == 'SUCCEEDED'
    assert apify_client_async_patcher.calls['actor']['start'] == []


async def test_auto_memoize_without_tracking_fails_init(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turning `auto_memoize_child_runs` on with child run tracking off makes the Actor start fail."""
    monkeypatch.setenv('APIFY_AUTO_MEMOIZE_CHILD_RUNS', 'true')

    with pytest.raises(ValueError, match='auto_memoize_child_runs'):
        await Actor(child_run_tracker=None).init()
