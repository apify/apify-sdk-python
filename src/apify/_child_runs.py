from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import timedelta
from logging import getLogger
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from pydantic.alias_generators import to_camel

from apify._utils import docs_group

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from apify_client import ApifyClientAsync
    from apify_client._models import Run
    from apify_client._resource_clients import RunClientAsync

    from apify.storages import KeyValueStore

logger = getLogger(__name__)

CHILD_RUNS_KEY = 'APIFY_CHILD_RUNS'
"""Key in the default key-value store under which the child run registry is persisted."""

_SETTLING_STATUSES = frozenset({'ABORTING', 'TIMING-OUT'})
"""Statuses that end as `ABORTED` / `TIMED-OUT` shortly, and are resurrectable once they do."""

_RESURRECTABLE_STATUSES = frozenset({'ABORTED', 'TIMED-OUT'})

_ABORTABLE_STATUSES = frozenset({'READY', 'RUNNING'})

_ACTIVE_STATUSES = frozenset({'READY', 'RUNNING', 'ABORTING', 'TIMING-OUT'})

_STATUS_MAX_AGE = timedelta(seconds=10)
"""How long an observed active status counts toward the concurrency limit before the run is fetched again."""


class ChildRunRecord(BaseModel):
    """A child run tracked under a name in the child run registry."""

    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    actor_id: str
    """The Actor ID or name the child was started with, as the caller passed it."""

    run_id: str
    """ID of the current run under this name."""

    previous_run_ids: list[str] = Field(default_factory=list)
    """IDs of earlier runs under this name that failed or went missing and were replaced by a new run, oldest first."""

    abort_with_parent: bool = False
    """Whether the current run is aborted when this Actor run is gracefully aborted."""


@docs_group('Actor')
@dataclass(frozen=True)
class ChildRunInfo:
    """A named child run of this Actor run, as returned by `Actor.child_runs`."""

    actor_id: str
    """The Actor ID or name the child was started with, as the caller passed it."""

    run_id: str
    """ID of the current run under this name."""

    run: Run | None
    """The current run as the API returns it now, or `None` when the platform no longer knows it."""

    previous_run_ids: list[str]
    """IDs of earlier runs under this name that failed or went missing and were replaced by a new run, oldest first."""

    abort_with_parent: bool
    """Whether the current run is aborted when this Actor run is gracefully aborted."""


_records_adapter = TypeAdapter(dict[str, ChildRunRecord])


class ChildRunRegistry:
    """Persisted name -> run map that lets named child runs survive a migration or resurrection of the parent.

    Every change is written to the key-value store right away. A hard kill of the parent between the platform
    starting the child and that write can still orphan the child, since nothing but the platform knows about it.
    """

    def __init__(self, open_key_value_store: Callable[[], Awaitable[KeyValueStore]]) -> None:
        self._open_key_value_store = open_key_value_store
        self._records: dict[str, ChildRunRecord] | None = None
        self._load_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._name_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._clients: dict[str, ApifyClientAsync] = {}
        """Client each name was last started or reattached with in this process, used to abort its run."""
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
        actor_id: str,
        client: ApifyClientAsync,
        start_run: Callable[[], Awaitable[Run]],
        resurrect_run: Callable[[RunClientAsync], Awaitable[Run]],
        abort_with_parent: bool = False,
    ) -> tuple[Run, bool]:
        """Return the run recorded under `name`, or start one when there is none to reuse.

        A recorded run that is `READY` or `RUNNING` is reattached and one that `SUCCEEDED` is returned as is.
        An `ABORTED` or `TIMED-OUT` run is resurrected, since Actors are expected to resume from their state.
        A `FAILED` run, or one the API no longer knows, is replaced by a new run under the same name.

        Starting or resurrecting a run waits while the concurrency limit is reached. Reattaching never waits.

        Args:
            name: Name of the child run, unique within the parent run.
            actor_id: The Actor to start. It must match the Actor already recorded under `name`.
            client: Client used to look up, resurrect and abort the recorded run.
            start_run: Starts a new run of the Actor.
            resurrect_run: Resurrects the recorded run, given its run client.
            abort_with_parent: Whether to abort the run when this Actor run is gracefully aborted. It replaces
                the value recorded under `name`.

        Returns:
            The run, and whether it was newly started.
        """
        async with self._name_locks[name]:
            records = await self._load()
            record = records.get(name)

            if record is not None and record.actor_id != actor_id:
                raise ValueError(
                    f'Child run "{name}" is already recorded for Actor "{record.actor_id}", '
                    f'it cannot be reused for Actor "{actor_id}".'
                )

            self._clients[name] = client

            if record is None:
                async with self._slot(name, client):
                    run = await self._start(
                        name,
                        actor_id=actor_id,
                        start_run=start_run,
                        previous_run_ids=[],
                        abort_with_parent=abort_with_parent,
                    )
                return run, True

            run_client = client.run(record.run_id)
            run = await run_client.get()

            if run is not None and run.status in _SETTLING_STATUSES:
                run = await run_client.wait_for_finish()

            if run is None or run.status == 'FAILED':
                async with self._slot(name, client):
                    run = await self._start(
                        name,
                        actor_id=actor_id,
                        start_run=start_run,
                        previous_run_ids=[*record.previous_run_ids, record.run_id],
                        abort_with_parent=abort_with_parent,
                    )
                return run, True

            self._observe(name, run)

            if record.abort_with_parent != abort_with_parent:
                await self._save(name, record.model_copy(update={'abort_with_parent': abort_with_parent}))

            if run.status in _RESURRECTABLE_STATUSES:
                async with self._slot(name, client):
                    logger.info(f'Resurrecting child run "{name}"', extra={'run_id': run.id, 'status': run.status})
                    run = await resurrect_run(run_client)
                    self._observe(name, run)
                return run, False

            logger.info(f'Reattaching to child run "{name}"', extra={'run_id': run.id, 'status': run.status})
            return run, False

    async def run_finished(self, name: str, run: Run) -> None:
        """Record the status of a run under `name` that was awaited, releasing its slot when it is no longer active."""
        records = await self._load()
        record = records.get(name)
        if record is None or record.run_id != run.id:
            return
        self._observe(name, run)
        async with self._slots:
            self._slots.notify_all()

    async def list_runs(self, client: ApifyClientAsync) -> dict[str, ChildRunInfo]:
        """Return every recorded child run by name, with its current state fetched from the API.

        Args:
            client: Client used to fetch the recorded runs.
        """
        # Copy the records, since a named start can add one while the runs are fetched.
        records = dict(await self._load())
        runs = await asyncio.gather(*(client.run(record.run_id).get() for record in records.values()))
        for (name, record), run in zip(records.items(), runs, strict=True):
            if run is not None and run.id == record.run_id:
                self._observe(name, run)
        return {
            name: ChildRunInfo(
                actor_id=record.actor_id,
                run_id=record.run_id,
                run=run,
                previous_run_ids=list(record.previous_run_ids),
                abort_with_parent=record.abort_with_parent,
            )
            for (name, record), run in zip(records.items(), runs, strict=True)
        }

    async def abort_runs_with_parent(self, client: ApifyClientAsync) -> None:
        """Gracefully abort every recorded run marked `abort_with_parent` that is still `READY` or `RUNNING`.

        A failure to abort one run is logged and does not stop the others.

        Args:
            client: Client used for a name not started or reattached in this process, e.g. after a migration.
        """
        self._parent_aborting = True
        async with self._slots:
            self._slots.notify_all()

        records = await self._load()
        # Names with a start in flight are not recorded yet, so their locks are awaited too.
        await asyncio.gather(*(self._abort(name, client) for name in {*records, *self._name_locks}))

    async def _abort(self, name: str, default_client: ApifyClientAsync) -> None:
        async with self._name_locks[name]:
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
        actor_id: str,
        start_run: Callable[[], Awaitable[Run]],
        previous_run_ids: list[str],
        abort_with_parent: bool,
    ) -> Run:
        run = await start_run()
        record = ChildRunRecord(
            actor_id=actor_id,
            run_id=run.id,
            previous_run_ids=previous_run_ids,
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

    async def _load(self) -> dict[str, ChildRunRecord]:
        async with self._load_lock:
            if self._records is None:
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

    async def _save(self, name: str, record: ChildRunRecord) -> None:
        records = await self._load()
        key_value_store = await self._open_key_value_store()
        async with self._write_lock:
            records[name] = record
            await key_value_store.set_value(
                CHILD_RUNS_KEY, _records_adapter.dump_python(records, by_alias=True, mode='json')
            )
