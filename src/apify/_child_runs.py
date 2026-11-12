from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from logging import getLogger
from typing import TYPE_CHECKING, Any, Literal, NamedTuple
from weakref import WeakValueDictionary

from pydantic import BaseModel, ConfigDict, Field, RootModel, ValidationError
from pydantic.alias_generators import to_camel

from apify_client._literals import ActorJobStatus
from apify_client.errors import NotFoundError
from crawlee._utils.recoverable_state import RecoverableState

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable, Coroutine

    from apify_client import ApifyClientAsync
    from apify_client._models import Run
    from apify_client._resource_clients import RunClientAsync

    from apify.storages import KeyValueStore

logger = getLogger(__name__)

CHILD_RUNS_KEY = '__ACTOR_CHILD_RUNS'
"""Key in the default key-value store under which the named child runs are persisted."""

UNNAMED_CHILD_RUNS_KEY = 'SDK_UNNAMED_CHILD_RUNS'
"""Key in the default key-value store under which the child runs started without a name are persisted."""

_SETTLING_STATUSES = frozenset({'ABORTING', 'TIMING-OUT'})
"""Statuses that end as `ABORTED` / `TIMED-OUT` shortly, and are resurrectable once they do."""

_RESURRECTABLE_STATUSES = frozenset({'ABORTED', 'TIMED-OUT'})
"""Statuses of a recorded run that a call under its name resurrects."""

_ABORTED_STATUSES = frozenset({'ABORTING', 'ABORTED'})
"""Statuses that show an abort request took effect on the child run."""

_ACTIVE_STATUSES = frozenset({'READY', 'RUNNING', 'ABORTING', 'TIMING-OUT'})
"""Statuses of a child run that count toward the concurrency limit."""

ChildRunStatus = ActorJobStatus | Literal['LOST']
"""Status of a child run, or `LOST` once the platform no longer returned it."""

_STATUS_MAX_AGE_SECS = 10
"""How long an observed active status counts toward the concurrency limit before the run is fetched again."""

_NOT_FOUND_GRACE_SECS = 3
"""How long a recorded run that the API reports as missing is looked up again before it counts as gone."""

_NOT_FOUND_RETRY_INTERVAL_SECS = 0.25
"""How long to wait between lookups of a recorded run that the API reports as missing."""


class ChildRunSnapshot(BaseModel):
    """A child run as last observed by this Actor run."""

    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    run_id: str
    """ID of the run."""

    status: ChildRunStatus
    """Last status of the run observed by this Actor run, or `LOST` once the platform no longer returned it."""

    started_at: datetime
    """When the run started."""


class ChildRunRecord(ChildRunSnapshot):
    """The current run tracked under a name in the child run registry, with the runs it replaced."""

    checksum: str
    """Hash of the Actor or task and the input the current run was started with."""

    history: list[ChildRunSnapshot] = Field(default_factory=list)
    """Earlier runs under this name that failed or went missing and were replaced by a new run, oldest first."""

    abort_with_parent: bool = False
    """Whether the current run is aborted when this Actor run is gracefully aborted."""


class UnnamedChildRunRecord(ChildRunSnapshot):
    """A child run started without a name, tracked under its run ID in the child run registry."""

    abort_with_parent: bool = False
    """Whether the run is aborted when this Actor run is gracefully aborted."""


class _CachedRunStatus(NamedTuple):
    """Status of a child run as this Actor run last saw it, used to count the run toward the concurrency limit."""

    status: ChildRunStatus
    """Status of the run, or `LOST` once the platform no longer returned it."""

    cached_at: float
    """Event loop time the status was seen at."""


def checksum_request(*, actor_id: str | None, task_id: str | None, run_input: Any) -> str:
    """Hash the Actor or task and the input of a named start, in the same JSON shape as the JS SDK."""
    request: dict[str, Any] = (
        {'type': 'actor', 'id': actor_id} if actor_id is not None else {'type': 'task', 'id': task_id}
    )
    if run_input is not None:
        request['input'] = run_input
    serialized = json.dumps(request, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


async def _get_recorded_run(run_client: RunClientAsync) -> Run | None:
    """Fetch a recorded run, retrying a 404 for a few seconds.

    A run started moments ago, e.g. by a concurrent call under the same name, may not be on every API replica yet,
    and treating it as gone would start a duplicate.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _NOT_FOUND_GRACE_SECS
    while True:
        run = await run_client.get()
        if run is not None or loop.time() >= deadline:
            return run
        await asyncio.sleep(_NOT_FOUND_RETRY_INTERVAL_SECS)


class _ChildRunRecords(RootModel[dict[str, ChildRunRecord]]):
    """Records of the child runs by name, in the shape persisted under `CHILD_RUNS_KEY`."""

    root: dict[str, ChildRunRecord] = Field(default_factory=dict)


class _UnnamedChildRunRecords(RootModel[dict[str, UnnamedChildRunRecord]]):
    """Records of the child runs started without a name, by run ID, as persisted under `UNNAMED_CHILD_RUNS_KEY`."""

    root: dict[str, UnnamedChildRunRecord] = Field(default_factory=dict)


class ChildRunRegistry:
    """Persisted record of the child runs of this Actor run, which survives a migration or resurrection of the parent.

    A named child run is recorded under its name, so a later start under the same name can reattach to it. A child run
    started without a name is recorded under its run ID. Every change is written to the key-value store right away. A
    hard kill of the parent between the platform starting the child and that write can still orphan the child, since
    nothing but the platform knows about it.
    """

    def __init__(
        self,
        open_key_value_store: Callable[[], Coroutine[Any, Any, KeyValueStore]],
        *,
        max_concurrent_runs: int | None = None,
    ) -> None:
        if max_concurrent_runs is not None and max_concurrent_runs < 1:
            raise ValueError(f'The child run concurrency limit must be at least 1, got {max_concurrent_runs}.')
        self._records = RecoverableState(
            default_state=_ChildRunRecords(),
            persist_state_key=CHILD_RUNS_KEY,
            persistence_enabled='explicit_only',
            persist_state_kvs_factory=open_key_value_store,
            logger=logger,
        )
        """Records of the child runs by name, persisted in the default key-value store on every change."""
        self._unnamed_records = RecoverableState(
            default_state=_UnnamedChildRunRecords(),
            persist_state_key=UNNAMED_CHILD_RUNS_KEY,
            persistence_enabled='explicit_only',
            persist_state_kvs_factory=open_key_value_store,
            logger=logger,
        )
        """Records of the child runs started without a name by run ID, persisted in the default key-value store on every
        change."""
        self._lock = asyncio.Lock()
        """Guards loading the records and writing them back to the key-value store."""
        self._name_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
        """Serializes `find_or_start` per name. A lock is dropped once no call under its name holds it."""
        self._clients: dict[str, ApifyClientAsync] = {}
        """Client each run was last started or looked up with, by run ID. Lost on a migration."""
        self._max_concurrent_runs = max_concurrent_runs
        """How many recorded runs, named or not, may be active at once, or `None` for no limit."""
        self._capacity_available = asyncio.Condition()
        """Wakes the waiting starts when capacity may be available."""
        self._starting_names: set[str] = set()
        """Names with a start or resurrection in flight, counted toward the limit but not from the records yet."""
        self._unnamed_starting = 0
        """How many starts without a name are in flight, counted toward the limit but not from the records yet."""
        self._run_status_cache: dict[str, _CachedRunStatus] = {}
        """Last seen status of each recorded run, by run ID. An active one is fetched again once it gets stale."""
        self._refresh_lock = asyncio.Lock()
        """Lets one waiting start at a time fetch the stale statuses, so the other waiting starts reuse them."""
        self._unnamed_starts_in_flight: set[asyncio.Event] = set()
        """Starts without a name and with `abort_with_parent` that are in flight, each set once the start ends."""
        self._parent_aborting = False
        """Whether this Actor run is being gracefully aborted, after which no run marked `abort_with_parent` starts,
        nor any run that would wait under the concurrency limit."""

    async def find_or_start(
        self,
        name: str,
        *,
        actor_id: str | None = None,
        task_id: str | None = None,
        run_input: Any,
        client: ApifyClientAsync,
        start_run: Callable[[], Awaitable[Run]],
        resurrect_run: Callable[[str], Awaitable[Run]],
        abort_with_parent: bool = False,
    ) -> tuple[Run, bool]:
        """Return the run recorded under `name`, or start one when there is none to reuse.

        A recorded run that is `READY` or `RUNNING` is reattached and one that `SUCCEEDED` is returned as is.
        An `ABORTED` or `TIMED-OUT` run is resurrected, since Actors are expected to resume from their state.
        A `FAILED` run, or one the API no longer knows, is replaced by a new run under the same name, for any Actor,
        task or input.

        Starting or resurrecting a run waits while the concurrency limit is reached. Reattaching never waits.

        Args:
            name: Name of the child run, unique within the parent run.
            actor_id: The Actor to start.
            task_id: The task to start, in place of `actor_id`.
            run_input: Input of the run. The recorded run is reused only if it was started with the same Actor or task
                and input.
            client: Client used to look up the recorded run.
            start_run: Starts a new run of the Actor or task.
            resurrect_run: Resurrects the recorded run, given its ID.
            abort_with_parent: Whether to abort the run when this Actor run is gracefully aborted. It replaces the value
                recorded under `name`.

        Returns:
            The run, and whether it was newly started.

        Raises:
            ValueError: If the recorded run would be reused, but was started for a different Actor, task or input.
            RuntimeError: If `abort_with_parent` is set and this Actor run is being gracefully aborted. No run is
                started, resurrected or reattached. Also if starting or resurrecting the run would wait under the
                concurrency limit while this Actor run is being gracefully aborted, whatever `abort_with_parent` is.
        """
        checksum = checksum_request(actor_id=actor_id, task_id=task_id, run_input=run_input)

        async with self._name_locks.setdefault(name, asyncio.Lock()):
            if abort_with_parent and self._parent_aborting:
                raise RuntimeError(
                    f'Child run "{name}" with `abort_with_parent` was not started, since this Actor run is being '
                    'aborted.'
                )

            records = await self._load()
            record = records.get(name)

            if record is None:
                async with self._reserve_capacity(name, client, abort_with_parent=abort_with_parent):
                    run = await self._start(
                        name, checksum=checksum, start_run=start_run, history=[], abort_with_parent=abort_with_parent
                    )
                self._clients[run.id] = client
                return run, True

            run_client = client.run(record.run_id)
            run = await _get_recorded_run(run_client)

            if run is not None and run.status in _SETTLING_STATUSES:
                run = await run_client.wait_for_finish()

            if run is None or run.status == 'FAILED':
                replaced = ChildRunSnapshot(
                    run_id=record.run_id,
                    status=run.status if run is not None else 'LOST',
                    started_at=record.started_at,
                )
                async with self._reserve_capacity(name, client, abort_with_parent=abort_with_parent):
                    run = await self._start(
                        name,
                        checksum=checksum,
                        start_run=start_run,
                        history=[*record.history, replaced],
                        abort_with_parent=abort_with_parent,
                    )
                self._clients[run.id] = client
                return run, True

            if record.checksum != checksum:
                raise ValueError(
                    f'The run name "{name}" was already used for a different Actor, task or input. '
                    'Use a unique `run_name` for each child run.'
                )

            self._cache_run_status(run)

            if record.abort_with_parent != abort_with_parent:
                await self._save(name, record.model_copy(update={'abort_with_parent': abort_with_parent}))

            if run.status in _RESURRECTABLE_STATUSES:
                async with self._reserve_capacity(name, client, abort_with_parent=abort_with_parent):
                    logger.info('Resurrecting child run "%s"', name, extra={'run_id': run.id, 'status': run.status})
                    run = await resurrect_run(run.id)
                    self._cache_run_status(run)
            else:
                logger.info('Reattaching to child run "%s"', name, extra={'run_id': run.id, 'status': run.status})

            await self.update(name, run)
            self._clients[run.id] = client
            return run, False

    async def start_unnamed(
        self,
        *,
        client: ApifyClientAsync,
        start_run: Callable[[], Awaitable[Run]],
        abort_with_parent: bool = False,
    ) -> Run:
        """Start a child run without a name and record it under its run ID.

        Starting the run waits while the concurrency limit is reached.

        Args:
            client: Client the run is started with.
            start_run: Starts a new run of the Actor or task.
            abort_with_parent: Whether to abort the run when this Actor run is gracefully aborted.

        Returns:
            The started run.

        Raises:
            RuntimeError: If `abort_with_parent` is set and this Actor run is being gracefully aborted. No run is
                started. Also if starting the run would wait under the concurrency limit while this Actor run is being
                gracefully aborted, whatever `abort_with_parent` is.
        """
        await self._load()
        if abort_with_parent and self._parent_aborting:
            raise RuntimeError(
                'Child run with `abort_with_parent` was not started, since this Actor run is being aborted.'
            )

        async with self._reserve_capacity(None, client, abort_with_parent=abort_with_parent):
            start_ended = asyncio.Event()
            if abort_with_parent:
                self._unnamed_starts_in_flight.add(start_ended)
            try:
                run = await start_run()
                self._clients[run.id] = client
                self._cache_run_status(run)
                await self._save_unnamed(
                    UnnamedChildRunRecord(
                        run_id=run.id,
                        status=run.status,
                        started_at=run.started_at,
                        abort_with_parent=abort_with_parent,
                    )
                )
            finally:
                self._unnamed_starts_in_flight.discard(start_ended)
                start_ended.set()
        return run

    def run_clients(self, default_client: ApifyClientAsync) -> dict[str, RunClientAsync]:
        """Return a client for the current run under each recorded name, and for each run recorded without a name.

        A named run is keyed by its name, a run started without a name by its run ID. Each client comes from the client
        its run was last started or looked up with in this process, so a run started with a custom token uses that
        token.

        Args:
            default_client: Client used for a run not started or looked up in this process, e.g. one recorded before a
                migration.
        """
        if not self._records.is_initialized:
            return {}
        run_ids = {
            **{run_id: run_id for run_id in self._unnamed_records.current_value.root},
            **{name: record.run_id for name, record in self._records.current_value.root.items()},
        }
        return {key: self._clients.get(run_id, default_client).run(run_id) for key, run_id in run_ids.items()}

    async def update(self, name: str | None, run: Run) -> None:
        """Record the latest observed status of the run recorded under `name`, or of a run started without a name.

        A run that is no longer active stops counting toward the concurrency limit.

        Args:
            name: Name of the child run, or `None` for a run started without a name.
            run: The run as just returned by the API. Nothing is recorded unless it is the current run under `name`, or
                a recorded run started without a name.
        """
        if name is None:
            await self._load()
            unnamed_record = self._unnamed_records.current_value.root.get(run.id)
            if unnamed_record is None:
                return
            self._cache_run_status(run)
            if unnamed_record.status != run.status:
                await self._save_unnamed(unnamed_record.model_copy(update={'status': run.status}))
            await self._notify_capacity_available()
            return

        record = (await self._load()).get(name)
        if record is None or record.run_id != run.id:
            return
        self._cache_run_status(run)
        if record.status != run.status:
            await self._save(name, record.model_copy(update={'status': run.status}))
        await self._notify_capacity_available()

    async def abort_runs_with_parent(self, client: ApifyClientAsync) -> None:
        """Gracefully abort every recorded run marked `abort_with_parent`, and refuse to start any more of them.

        Each run gets one abort request, all in parallel. The platform leaves a run that already finished as it is. A
        failure to abort one run is logged and does not stop the others. A run whose start is in flight is aborted once
        the start records it.

        Args:
            client: Client used for a run not started or looked up in this process, e.g. after a migration.
        """
        self._parent_aborting = True
        await self._notify_capacity_available()
        records = await self._load()
        # Names with a start in flight are not recorded yet, so their locks are awaited too.
        await asyncio.gather(
            *(self._abort(name, client) for name in {*records, *self._name_locks}),
            self._abort_unnamed(client),
        )

    async def _abort(self, name: str, default_client: ApifyClientAsync) -> None:
        async with self._name_locks.setdefault(name, asyncio.Lock()):
            record = (await self._load()).get(name)
            if record is None or not record.abort_with_parent:
                return
            await self._abort_run(name, record.run_id, default_client)

    async def _abort_unnamed(self, default_client: ApifyClientAsync) -> None:
        # Starts in flight are not recorded yet, so they are awaited first.
        await asyncio.gather(*(start_ended.wait() for start_ended in [*self._unnamed_starts_in_flight]))
        await asyncio.gather(
            *(
                self._abort_run(run_id, run_id, default_client)
                for run_id, record in self._unnamed_records.current_value.root.items()
                if record.abort_with_parent
            )
        )

    async def _abort_run(self, label: str, run_id: str, default_client: ApifyClientAsync) -> None:
        """Send one graceful abort request to a child run, logging the outcome under `label`."""
        run_client = self._clients.get(run_id, default_client).run(run_id)
        try:
            run = await run_client.abort(gracefully=True)
        except NotFoundError:
            logger.debug('Child run "%s" no longer exists', label, extra={'run_id': run_id})
        except Exception:
            logger.exception('Failed to abort child run "%s"', label, extra={'run_id': run_id})
        else:
            if run.status in _ABORTED_STATUSES:
                logger.info('Aborted child run "%s" with the parent', label, extra={'run_id': run_id})

    async def _start(
        self,
        name: str,
        *,
        checksum: str,
        start_run: Callable[[], Awaitable[Run]],
        history: list[ChildRunSnapshot],
        abort_with_parent: bool,
    ) -> Run:
        run = await start_run()
        record = ChildRunRecord(
            run_id=run.id,
            status=run.status,
            started_at=run.started_at,
            checksum=checksum,
            history=history,
            abort_with_parent=abort_with_parent,
        )
        await self._save(name, record)
        self._cache_run_status(run)
        return run

    @asynccontextmanager
    async def _reserve_capacity(
        self, name: str | None, client: ApifyClientAsync, *, abort_with_parent: bool
    ) -> AsyncGenerator[None]:
        """Count starting or resurrecting the run under `name` toward the limit, waiting while the limit is reached.

        Args:
            name: Name of the run, or `None` for a run started without a name.
            client: Client used to fetch stale statuses of runs not started or looked up in this process.
            abort_with_parent: Whether the run is aborted with this Actor run, so it must not start once that aborts.
        """
        label = 'Child run' if name is None else f'Child run "{name}"'
        while self._max_concurrent_runs is not None:
            await self._refresh_stale_statuses(client)
            async with self._capacity_available:
                # No await separates this count from the reservation below, so two starts can't both pass it and go
                # over the limit.
                if self._count_active(exclude=name) < self._max_concurrent_runs:
                    break
                if self._parent_aborting:
                    raise RuntimeError(
                        f'{label} was not started, since this Actor run is being aborted and the limit of '
                        f'{self._max_concurrent_runs} concurrent child runs is reached.'
                    )
                logger.debug('%s is waiting for the concurrency limit', label)
                with suppress(TimeoutError):
                    async with asyncio.timeout(_STATUS_MAX_AGE_SECS):
                        await self._capacity_available.wait()
        # The parent can start aborting while this start waits.
        if abort_with_parent and self._parent_aborting:
            raise RuntimeError(
                f'{label} with `abort_with_parent` was not started, since this Actor run is being aborted.'
            )

        if name is None:
            self._unnamed_starting += 1
        else:
            self._starting_names.add(name)
        try:
            yield
        finally:
            if name is None:
                self._unnamed_starting -= 1
            else:
                self._starting_names.discard(name)
            await self._notify_capacity_available()

    async def _refresh_stale_statuses(self, client: ApifyClientAsync) -> None:
        """Fetch the active runs whose last seen status is stale, so a run that finished stops counting."""
        await self._load()
        async with self._refresh_lock:
            now = asyncio.get_running_loop().time()
            stale = [(label, record) for label, record in self._counted_records() if self._is_stale(record, now)]
            cached_before_fetch = {record.run_id: self._run_status_cache.get(record.run_id) for _, record in stale}
            runs = await asyncio.gather(
                *(self._clients.get(record.run_id, client).run(record.run_id).get() for _, record in stale),
                return_exceptions=True,
            )

            # A run that could not be fetched keeps its last seen status, so it counts while it was last seen active. A
            # status seen during the fetch, e.g. by `update` once a call awaited the run, is newer than the fetched one.
            for (label, record), run in zip(stale, runs, strict=True):
                if self._run_status_cache.get(record.run_id) is not cached_before_fetch[record.run_id]:
                    continue
                if isinstance(run, BaseException):
                    logger.warning(
                        'Failed to fetch child run "%s" to count it toward the concurrency limit',
                        label,
                        extra={'run_id': record.run_id},
                        exc_info=run,
                    )
                elif run is None:
                    self._run_status_cache[record.run_id] = _CachedRunStatus('LOST', now)
                else:
                    self._cache_run_status(run)

    def _is_stale(self, record: ChildRunSnapshot, now: float) -> bool:
        """Whether the recorded run was last seen active long enough ago to be fetched before counting it."""
        cached_run_status = self._run_status_cache.get(record.run_id)
        if cached_run_status is None:
            return record.status in _ACTIVE_STATUSES
        return (
            cached_run_status.status in _ACTIVE_STATUSES and now - cached_run_status.cached_at >= _STATUS_MAX_AGE_SECS
        )

    def _count_active(self, *, exclude: str | None) -> int:
        """Count the active runs and the starts in flight, apart from the recorded run under the name `exclude`."""
        active = sum(
            1
            for label, record in self._counted_records()
            if label != exclude and self._last_status(record) in _ACTIVE_STATUSES
        )
        return active + len(self._starting_names) + self._unnamed_starting

    def _counted_records(self) -> list[tuple[str, ChildRunSnapshot]]:
        """List the recorded runs that count by their status, each with its name, or its run ID for an unnamed run.

        A name with a start in flight is left out, since the start counts in its place.
        """
        named = [
            (name, record)
            for name, record in self._records.current_value.root.items()
            if name not in self._starting_names
        ]
        return [*named, *self._unnamed_records.current_value.root.items()]

    def _last_status(self, record: ChildRunSnapshot) -> ChildRunStatus:
        cached_run_status = self._run_status_cache.get(record.run_id)
        return cached_run_status.status if cached_run_status is not None else record.status

    async def _notify_capacity_available(self) -> None:
        async with self._capacity_available:
            self._capacity_available.notify_all()

    def _cache_run_status(self, run: Run) -> None:
        self._run_status_cache[run.id] = _CachedRunStatus(run.status, asyncio.get_running_loop().time())

    async def load(self) -> dict[str, ChildRunRecord]:
        """Read the records from the default key-value store, replacing any read before."""
        async with self._lock:
            for key, state in ((UNNAMED_CHILD_RUNS_KEY, self._unnamed_records), (CHILD_RUNS_KEY, self._records)):
                try:
                    await state.initialize()
                except ValidationError as exc:
                    raise ValueError(
                        f'The child run registry under the "{key}" key in the default key-value store is malformed.'
                    ) from exc
            return self._records.current_value.root

    async def _load(self) -> dict[str, ChildRunRecord]:
        return self._records.current_value.root if self._records.is_initialized else await self.load()

    async def _save(self, name: str, record: ChildRunRecord) -> None:
        await self._load()
        async with self._lock:
            self._records.current_value.root[name] = record
            await self._records.persist_state()

    async def _save_unnamed(self, record: UnnamedChildRunRecord) -> None:
        await self._load()
        async with self._lock:
            self._unnamed_records.current_value.root[record.run_id] = record
            await self._unnamed_records.persist_state()
