from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta
from logging import getLogger
from typing import TYPE_CHECKING, Any
from weakref import WeakValueDictionary

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from pydantic.alias_generators import to_camel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from apify_client import ApifyClientAsync
    from apify_client._models import Run
    from apify_client._resource_clients import RunClientAsync

    from apify.storages import KeyValueStore

logger = getLogger(__name__)

CHILD_RUNS_KEY = '__ACTOR_CHILD_RUNS'
"""Key in the default key-value store under which the child run registry is persisted."""

_SETTLING_STATUSES = frozenset({'ABORTING', 'TIMING-OUT'})
"""Statuses that end as `ABORTED` / `TIMED-OUT` shortly, and are resurrectable once they do."""

_RESURRECTABLE_STATUSES = frozenset({'ABORTED', 'TIMED-OUT'})

_ABORTABLE_STATUSES = frozenset({'READY', 'RUNNING'})

_ACTIVE_STATUSES = frozenset({'READY', 'RUNNING', 'ABORTING', 'TIMING-OUT'})

_STATUS_MAX_AGE = timedelta(seconds=10)
"""How long an observed active status counts toward the concurrency limit before the run is fetched again."""

_NOT_FOUND_GRACE_SECS = 3
"""How long a recorded run that the API reports as missing is looked up again before it counts as gone."""

_NOT_FOUND_RETRY_INTERVAL_SECS = 0.25


class ChildRunSnapshot(BaseModel):
    """A child run as last observed by this Actor run."""

    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    run_id: str
    """ID of the run."""

    status: str
    """Last status of the run observed by this Actor run, or `LOST` once the platform no longer returned it."""

    started_at: datetime
    """When the run started."""


class ChildRunRecord(ChildRunSnapshot):
    """The current run tracked under a name in the child run registry, with the runs it replaced."""

    checksum: str
    """Hash of the Actor or task and the input the name was first used with."""

    history: list[ChildRunSnapshot] = Field(default_factory=list)
    """Earlier runs under this name that failed or went missing and were replaced by a new run, oldest first."""

    abort_with_parent: bool = False
    """Whether the current run is aborted when this Actor run is gracefully aborted."""


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


_records_adapter = TypeAdapter(dict[str, ChildRunRecord])


class ChildRunRegistry:
    """Persisted name -> run map that lets named child runs survive a migration or resurrection of the parent.

    Every change is written to the key-value store right away. A hard kill of the parent between the platform
    starting the child and that write can still orphan the child, since nothing but the platform knows about it.
    """

    def __init__(self, open_key_value_store: Callable[[], Awaitable[KeyValueStore]]) -> None:
        self._open_key_value_store = open_key_value_store
        self._records: dict[str, ChildRunRecord] | None = None
        self._lock = asyncio.Lock()
        """Guards loading the records and writing them back to the key-value store."""
        self._name_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
        """Serializes `find_or_start` per name. A lock is dropped once no call under its name holds it."""
        self._clients: dict[str, ApifyClientAsync] = {}
        """Client the run under each name was last started or looked up with. Lost on a migration."""
        self._max_concurrent_runs: int | None = None
        self._slots = asyncio.Condition()
        self._starting: set[str] = set()
        """Names holding a slot for a start or resurrection in flight, not counted from the records yet."""
        self._observed: dict[str, tuple[str, float]] = {}
        """Last observed status of the run recorded under each name, with the event loop time it was observed at."""
        self._parent_aborting = False

    def set_max_concurrent_runs(self, max_concurrent_runs: int | None) -> None:
        """Set how many recorded runs may be active at once, or remove the limit with `None`."""
        if max_concurrent_runs is not None and max_concurrent_runs < 1:
            raise ValueError(f'`max_concurrent_runs` must be at least 1, got {max_concurrent_runs}.')
        self._max_concurrent_runs = max_concurrent_runs

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
        A `FAILED` run, or one the API no longer knows, is replaced by a new run under the same name.

        Starting or resurrecting a run waits while the concurrency limit is reached. Reattaching never waits.

        Args:
            name: Name of the child run, unique within the parent run.
            actor_id: The Actor to start.
            task_id: The task to start, in place of `actor_id`.
            run_input: Input of the run. With the Actor or task, it must match what `name` was first used with.
            client: Client used to look up the recorded run.
            start_run: Starts a new run of the Actor or task.
            resurrect_run: Resurrects the recorded run, given its ID.
            abort_with_parent: Whether to abort the run when this Actor run is gracefully aborted. It replaces the value
                recorded under `name`.

        Returns:
            The run, and whether it was newly started.
        """
        checksum = checksum_request(actor_id=actor_id, task_id=task_id, run_input=run_input)

        async with self._name_locks.setdefault(name, asyncio.Lock()):
            records = await self._load()
            record = records.get(name)

            if record is not None and record.checksum != checksum:
                raise ValueError(
                    f'The run name "{name}" was already used for a different Actor, task or input. '
                    'Use a unique `run_name` for each child run.'
                )

            if record is None:
                async with self._slot(name, client):
                    run = await self._start(
                        name, checksum=checksum, start_run=start_run, history=[], abort_with_parent=abort_with_parent
                    )
                self._clients[name] = client
                return run, True

            run_client = client.run(record.run_id)
            run = await _get_recorded_run(run_client)
            self._clients[name] = client

            if run is not None and run.status in _SETTLING_STATUSES:
                run = await run_client.wait_for_finish()

            if run is None or run.status == 'FAILED':
                replaced = ChildRunSnapshot(
                    run_id=record.run_id,
                    status=run.status if run is not None else 'LOST',
                    started_at=record.started_at,
                )
                async with self._slot(name, client):
                    run = await self._start(
                        name,
                        checksum=checksum,
                        start_run=start_run,
                        history=[*record.history, replaced],
                        abort_with_parent=abort_with_parent,
                    )
                return run, True

            self._observe(name, run)

            if record.abort_with_parent != abort_with_parent:
                await self._save(name, record.model_copy(update={'abort_with_parent': abort_with_parent}))

            if run.status in _RESURRECTABLE_STATUSES:
                async with self._slot(name, client):
                    logger.info(f'Resurrecting child run "{name}"', extra={'run_id': run.id, 'status': run.status})
                    run = await resurrect_run(run.id)
                    self._observe(name, run)
            else:
                logger.info(f'Reattaching to child run "{name}"', extra={'run_id': run.id, 'status': run.status})

            await self.update(name, run)
            return run, False

    def run_clients(self, default_client: ApifyClientAsync) -> dict[str, RunClientAsync]:
        """Return a client for the current run under each recorded name.

        Each client comes from the client its name was last started or looked up with in this process, so a run started
        with a custom token uses that token.

        Args:
            default_client: Client used for a name not started or looked up in this process, e.g. one recorded before a
                migration.
        """
        return {
            name: self._clients.get(name, default_client).run(record.run_id)
            for name, record in (self._records or {}).items()
        }

    async def update(self, name: str, run: Run) -> None:
        """Record the latest observed status of the run recorded under `name`.

        A run that is no longer active releases its slot under the concurrency limit.

        Args:
            name: Name of the child run.
            run: The run as just returned by the API. Nothing is recorded unless it is the current run under `name`.
        """
        record = (await self._load()).get(name)
        if record is None or record.run_id != run.id:
            return
        self._observe(name, run)
        if record.status != run.status:
            await self._save(name, record.model_copy(update={'status': run.status}))
        async with self._slots:
            self._slots.notify_all()

    async def abort_runs_with_parent(self, client: ApifyClientAsync) -> None:
        """Gracefully abort every recorded run marked `abort_with_parent` that is still `READY` or `RUNNING`.

        A failure to abort one run is logged and does not stop the others.

        Args:
            client: Client used for a name not started or looked up in this process, e.g. after a migration.
        """
        self._parent_aborting = True
        async with self._slots:
            self._slots.notify_all()

        records = await self._load()
        # Names with a start in flight are not recorded yet, so their locks are awaited too.
        await asyncio.gather(*(self._abort(name, client) for name in {*records, *self._name_locks}))

    async def _abort(self, name: str, default_client: ApifyClientAsync) -> None:
        async with self._name_locks.setdefault(name, asyncio.Lock()):
            record = (await self._load()).get(name)
            if record is None or not record.abort_with_parent:
                return
            run_client = self._clients.get(name, default_client).run(record.run_id)
            try:
                run = await run_client.get()
                if run is None or run.status not in _ABORTABLE_STATUSES:
                    return
                await run_client.abort(gracefully=True)
            except Exception:
                logger.exception(f'Failed to abort child run "{name}"', extra={'run_id': record.run_id})
            else:
                logger.info(f'Aborted child run "{name}" with the parent', extra={'run_id': record.run_id})

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
        self._observe(name, run)
        return run

    @asynccontextmanager
    async def _slot(self, name: str, client: ApifyClientAsync) -> AsyncIterator[None]:
        """Hold a slot for starting or resurrecting the run under `name`, waiting while the limit is reached."""
        if self._max_concurrent_runs is None:
            yield
            return

        async with self._slots:
            while (
                self._max_concurrent_runs is not None
                and await self._count_active(client, exclude=name) >= self._max_concurrent_runs
            ):
                if self._parent_aborting:
                    raise RuntimeError(
                        f'Child run "{name}" was not started, since this Actor run is being aborted and the limit '
                        f'of {self._max_concurrent_runs} concurrent child runs is reached.'
                    )
                logger.debug(f'Child run "{name}" is waiting for a free slot')
                with suppress(TimeoutError):
                    await asyncio.wait_for(self._slots.wait(), timeout=_STATUS_MAX_AGE.total_seconds())
            self._starting.add(name)

        try:
            yield
        finally:
            self._starting.discard(name)
            async with self._slots:
                self._slots.notify_all()

    async def _count_active(self, client: ApifyClientAsync, *, exclude: str) -> int:
        """Count active recorded runs and slots held by others, fetching runs whose active status is not fresh."""
        records = await self._load()
        names = [name for name in records if name != exclude and name not in self._starting]
        now = asyncio.get_running_loop().time()
        stale = [
            name
            for name in names
            if name not in self._observed
            or (
                self._observed[name][0] in _ACTIVE_STATUSES
                and now - self._observed[name][1] >= _STATUS_MAX_AGE.total_seconds()
            )
        ]
        runs = await asyncio.gather(
            *(self._clients.get(name, client).run(records[name].run_id).get() for name in stale),
            return_exceptions=True,
        )
        for name, run in zip(stale, runs, strict=True):
            if isinstance(run, BaseException):
                logger.warning(
                    f'Failed to fetch child run "{name}" to count it toward the concurrency limit',
                    extra={'run_id': records[name].run_id},
                    exc_info=run,
                )
            elif run is None:
                self._observed[name] = ('MISSING', now)
            else:
                self._observe(name, run)

        # A run that could not be fetched counts only when an earlier observation saw it active.
        active = sum(1 for name in names if name in self._observed and self._observed[name][0] in _ACTIVE_STATUSES)
        return active + len(self._starting)

    def _observe(self, name: str, run: Run) -> None:
        self._observed[name] = (run.status, asyncio.get_running_loop().time())

    async def load(self) -> dict[str, ChildRunRecord]:
        """Read the records from the default key-value store, replacing any read before."""
        async with self._lock:
            key_value_store = await self._open_key_value_store()
            stored = await key_value_store.get_value(CHILD_RUNS_KEY)
            try:
                self._records = _records_adapter.validate_python(stored or {})
            except ValidationError as exc:
                raise ValueError(
                    f'The child run registry under the "{CHILD_RUNS_KEY}" key in the default key-value store '
                    'is malformed.'
                ) from exc
            return self._records

    async def _load(self) -> dict[str, ChildRunRecord]:
        return self._records if self._records is not None else await self.load()

    async def _save(self, name: str, record: ChildRunRecord) -> None:
        records = await self._load()
        key_value_store = await self._open_key_value_store()
        async with self._lock:
            records[name] = record
            await key_value_store.set_value(
                CHILD_RUNS_KEY, _records_adapter.dump_python(records, by_alias=True, mode='json')
            )
