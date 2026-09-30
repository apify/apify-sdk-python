from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from logging import getLogger
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from pydantic.alias_generators import to_camel

from apify._utils import docs_group

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from apify_client import ApifyClientAsync
    from apify_client._models import Run
    from apify_client._resource_clients import RunClientAsync

    from apify._charging import ChargingManagerImplementation
    from apify.storages import KeyValueStore

logger = getLogger(__name__)

CHILD_RUNS_KEY = 'APIFY_CHILD_RUNS'
"""Key in the default key-value store under which the child run registry is persisted."""

_SETTLING_STATUSES = frozenset({'ABORTING', 'TIMING-OUT'})
"""Statuses that end as `ABORTED` / `TIMED-OUT` shortly, and are resurrectable once they do."""

_RESURRECTABLE_STATUSES = frozenset({'ABORTED', 'TIMED-OUT'})

_ABORTABLE_STATUSES = frozenset({'READY', 'RUNNING'})

_ACTIVE_STATUSES = frozenset({'READY', 'RUNNING', 'ABORTING', 'TIMING-OUT'})

_TERMINAL_STATUSES = frozenset({'SUCCEEDED', 'FAILED', 'ABORTED', 'TIMED-OUT'})

_STATUS_MAX_AGE = timedelta(seconds=10)
"""How long an observed active status counts toward the concurrency limit before the run is fetched again."""

_CHARGE_SETTLE_TIME = timedelta(minutes=3)
"""How long after a run finishes the platform may still add to its `usage_total_usd`."""


class StartRun(Protocol):
    """Starts a new run of the Actor with the given charge limit."""

    def __call__(self, *, max_total_charge_usd: Decimal | None) -> Awaitable[Run]: ...


class ResurrectRun(Protocol):
    """Resurrects the recorded run, given its run client, with the given charge limit."""

    def __call__(self, run_client: RunClientAsync, *, max_total_charge_usd: Decimal | None) -> Awaitable[Run]: ...


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

    max_total_charge_usd: Decimal | None = None
    """Charge limit of the current run reserved from this Actor run's budget, or `None` when nothing is reserved."""

    charged_usd: Decimal | None = None
    """Final charge of the current run, set once it finished and its `usage_total_usd` settled."""

    previous_charged_usd: Decimal = Decimal(0)
    """Charges of the earlier runs under this name, still counted against this Actor run's budget."""


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

    max_total_charge_usd: Decimal | None
    """Charge limit of the current run reserved from this Actor run's budget, or `None` when nothing is reserved."""


_records_adapter = TypeAdapter(dict[str, ChildRunRecord])


class ChildRunRegistry:
    """Persisted name -> run map that lets named child runs survive a migration or resurrection of the parent.

    Every change is written to the key-value store right away. A hard kill of the parent between the platform
    starting the child and that write can still orphan the child, since nothing but the platform knows about it.
    """

    def __init__(
        self,
        open_key_value_store: Callable[[], Awaitable[KeyValueStore]],
        get_charging_manager: Callable[[], ChargingManagerImplementation] | None = None,
    ) -> None:
        self._open_key_value_store = open_key_value_store
        self._get_charging_manager = get_charging_manager
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
        self._reserving: dict[str, Decimal] = {}
        """Charge limits reserved for starts and resurrections in flight, not recorded yet."""
        self._unsettled_charges: dict[str, Decimal] = {}
        """Charge of each finished current run whose `usage_total_usd` may still grow, as last observed."""
        self._resurrected_after: dict[str, datetime] = {}
        """When the current run under each name finished before it was resurrected, to ignore older snapshots of it."""

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
        start_run: StartRun,
        resurrect_run: ResurrectRun,
        abort_with_parent: bool = False,
        max_total_charge_usd: Decimal | None = None,
    ) -> tuple[Run, bool]:
        """Return the run recorded under `name`, or start one when there is none to reuse.

        A recorded run that is `READY` or `RUNNING` is reattached and one that `SUCCEEDED` is returned as is.
        An `ABORTED` or `TIMED-OUT` run is resurrected, since Actors are expected to resume from their state.
        A `FAILED` run, or one the API no longer knows, is replaced by a new run under the same name.

        Starting or resurrecting a run waits while the concurrency limit is reached. Reattaching never waits.

        When this Actor run has a `max_total_charge_usd` set by the user, a started or resurrected run gets at most
        the part of it that is not charged yet nor reserved for other child runs, and that part stays reserved for the
        run until it finishes. A reattached run keeps the limit it was started with.

        Args:
            name: Name of the child run, unique within the parent run.
            actor_id: The Actor to start. It must match the Actor already recorded under `name`.
            client: Client used to look up, resurrect and abort the recorded run.
            start_run: Starts a new run of the Actor.
            resurrect_run: Resurrects the recorded run, given its run client.
            abort_with_parent: Whether to abort the run when this Actor run is gracefully aborted. It replaces
                the value recorded under `name`.
            max_total_charge_usd: Charge limit for a started or resurrected run, lowered to the budget left.

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
                async with (
                    self._slot(name, client),
                    self._budget(name, client, max_total_charge_usd) as (limit, reserved),
                ):
                    run = await self._start(
                        name,
                        actor_id=actor_id,
                        start_run=start_run,
                        previous_run_ids=[],
                        abort_with_parent=abort_with_parent,
                        max_total_charge_usd=limit,
                        reserved_usd=reserved,
                        previous_charged_usd=Decimal(0),
                    )
                return run, True

            run_client = client.run(record.run_id)
            run = await run_client.get()

            if run is not None and run.status in _SETTLING_STATUSES:
                run = await run_client.wait_for_finish()

            if run is not None:
                await self._settle_charge(name, run)
                record = records[name]

            if run is None or run.status == 'FAILED':
                async with (
                    self._slot(name, client),
                    self._budget(name, client, max_total_charge_usd) as (limit, reserved),
                ):
                    run = await self._start(
                        name,
                        actor_id=actor_id,
                        start_run=start_run,
                        previous_run_ids=[*record.previous_run_ids, record.run_id],
                        abort_with_parent=abort_with_parent,
                        max_total_charge_usd=limit,
                        reserved_usd=reserved,
                        previous_charged_usd=record.previous_charged_usd + self._current_charge(name, record),
                    )
                return run, True

            self._observe(name, run)

            if record.abort_with_parent != abort_with_parent:
                await self._save(name, record.model_copy(update={'abort_with_parent': abort_with_parent}))

            if run.status in _RESURRECTABLE_STATUSES:
                async with (
                    self._slot(name, client),
                    self._budget(name, client, max_total_charge_usd, replaces_current=True) as (limit, reserved),
                ):
                    logger.info(f'Resurrecting child run "{name}"', extra={'run_id': run.id, 'status': run.status})
                    finished_at = run.finished_at
                    run = await resurrect_run(run_client, max_total_charge_usd=limit)
                    if finished_at is not None:
                        self._resurrected_after[name] = finished_at
                    self._unsettled_charges.pop(name, None)
                    await self._save(
                        name, records[name].model_copy(update={'max_total_charge_usd': reserved, 'charged_usd': None})
                    )
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
        await self._settle_charge(name, run)
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
        # A name whose run was replaced during the fetch keeps the status observed for its new run.
        current = await self._load()
        for name, run in zip(records, runs, strict=True):
            if run is not None and name in current and current[name].run_id == run.id:
                self._observe(name, run)
                await self._settle_charge(name, run)
        return {
            name: ChildRunInfo(
                actor_id=record.actor_id,
                run_id=record.run_id,
                run=run,
                previous_run_ids=list(record.previous_run_ids),
                abort_with_parent=record.abort_with_parent,
                max_total_charge_usd=record.max_total_charge_usd,
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
        start_run: StartRun,
        previous_run_ids: list[str],
        abort_with_parent: bool,
        max_total_charge_usd: Decimal | None,
        reserved_usd: Decimal | None,
        previous_charged_usd: Decimal,
    ) -> Run:
        run = await start_run(max_total_charge_usd=max_total_charge_usd)
        record = ChildRunRecord(
            actor_id=actor_id,
            run_id=run.id,
            previous_run_ids=previous_run_ids,
            abort_with_parent=abort_with_parent,
            max_total_charge_usd=reserved_usd,
            previous_charged_usd=previous_charged_usd,
        )
        self._unsettled_charges.pop(name, None)
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

    def reserved_usd(self) -> Decimal:
        """Return the part of this Actor run's budget reserved for or charged by its named child runs."""
        records = self._records or {}
        return sum(
            (record.previous_charged_usd + self._current_charge(name, record) for name, record in records.items()),
            start=sum(self._reserving.values(), start=Decimal(0)),
        )

    async def load(self) -> None:
        """Load the records persisted by an earlier attempt of this Actor run, so their reservations count."""
        await self._load()

    def _current_charge(self, name: str, record: ChildRunRecord) -> Decimal:
        """Return the charge of the current run under `name`, or its whole limit while it may still grow."""
        if record.charged_usd is not None:
            return record.charged_usd
        if name in self._unsettled_charges:
            return self._unsettled_charges[name]
        return record.max_total_charge_usd or Decimal(0)

    async def _settle_charge(self, name: str, run: Run) -> None:
        """Release the unused part of the limit of a finished current run, recording its charge once it settled."""
        record = (await self._load()).get(name)
        if (
            record is None
            or record.run_id != run.id
            or record.max_total_charge_usd is None
            or record.charged_usd is not None
            or run.status not in _TERMINAL_STATUSES
            or run.usage_total_usd is None
            # A snapshot fetched before a resurrection shows the run as it finished the previous time.
            or (
                name in self._resurrected_after
                and run.finished_at is not None
                and run.finished_at <= self._resurrected_after[name]
            )
        ):
            return

        charged_usd = Decimal(str(run.usage_total_usd))
        if run.finished_at is not None and datetime.now(UTC) - run.finished_at >= _CHARGE_SETTLE_TIME:
            await self._save(name, record.model_copy(update={'charged_usd': charged_usd}), if_unchanged=record)
            self._unsettled_charges.pop(name, None)
        else:
            self._unsettled_charges[name] = charged_usd

    @asynccontextmanager
    async def _budget(
        self,
        name: str,
        client: ApifyClientAsync,
        max_total_charge_usd: Decimal | None,
        *,
        replaces_current: bool = False,
    ) -> AsyncIterator[tuple[Decimal | None, Decimal | None]]:
        """Reserve a charge limit for starting or resurrecting the run under `name`, capped at the budget left.

        Yields the limit to start the run with, and the part of it reserved from this Actor run's budget. Nothing is
        reserved when this Actor run has no budget set by the user.

        Args:
            name: Name of the child run.
            client: Client used to fetch recorded runs whose charge is not settled.
            max_total_charge_usd: The requested limit, or `None` for all of the budget left.
            replaces_current: Whether the new limit replaces the one of the current run under `name`, as a
                resurrection does, so that one's reservation is available to it.
        """
        charging_manager = self._get_charging_manager() if self._get_charging_manager else None
        if charging_manager is None or not await charging_manager.is_max_total_charge_usd_set_by_user():
            yield max_total_charge_usd, None
            return

        await self._refresh_charges(client, exclude=name)
        async with charging_manager.charge_lock():
            available = charging_manager.calculate_remaining_budget()
            record = (await self._load()).get(name)
            current_charge = self._current_charge(name, record) if replaces_current and record is not None else 0
            available += current_charge
            if available <= 0:
                raise RuntimeError(
                    f'Child run "{name}" was not started, since the budget of this Actor run is spent or reserved for '
                    'other child runs.'
                )
            limit = available if max_total_charge_usd is None else min(max_total_charge_usd, available)
            if max_total_charge_usd is not None and limit < max_total_charge_usd:
                logger.info(
                    f'Lowering the charge limit of child run "{name}" to {limit} USD, the budget left for it',
                    extra={'requested_usd': str(max_total_charge_usd)},
                )
            # A resurrected run's current charge is reserved by its record already.
            self._reserving[name] = max(limit - current_charge, Decimal(0))

        try:
            yield limit, limit
        finally:
            self._reserving.pop(name, None)

    async def _refresh_charges(self, client: ApifyClientAsync, *, exclude: str) -> None:
        """Fetch recorded runs whose charge is not settled, releasing the unused limit of those that finished."""
        records = await self._load()
        now = asyncio.get_running_loop().time()
        names = [
            name
            for name, record in records.items()
            if name != exclude
            and name not in self._reserving
            and record.max_total_charge_usd is not None
            and record.charged_usd is None
            # A run seen active a moment ago still holds its whole limit.
            and not (
                name in self._observed
                and self._observed[name][0] in _ACTIVE_STATUSES
                and now - self._observed[name][1] < _STATUS_MAX_AGE.total_seconds()
            )
        ]
        runs = await asyncio.gather(
            *(self._clients.get(name, client).run(records[name].run_id).get() for name in names),
            return_exceptions=True,
        )
        for name, run in zip(names, runs, strict=True):
            if isinstance(run, BaseException):
                logger.warning(
                    f'Failed to fetch child run "{name}" to release its unused budget',
                    extra={'run_id': records[name].run_id},
                    exc_info=run,
                )
            elif run is not None:
                self._observe(name, run)
                await self._settle_charge(name, run)

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

    async def _save(self, name: str, record: ChildRunRecord, *, if_unchanged: ChildRunRecord | None = None) -> None:
        """Record `record` under `name`.

        With `if_unchanged`, the write is skipped when `name` no longer holds that record, and a reservation of a start
        or resurrection in flight is left alone.
        """
        records = await self._load()
        key_value_store = await self._open_key_value_store()
        async with self._write_lock:
            if if_unchanged is not None:
                if records.get(name) is not if_unchanged:
                    return
            else:
                # The record carries the limit reserved for a start or resurrection in flight from here on.
                self._reserving.pop(name, None)
            records[name] = record
            await key_value_store.set_value(
                CHILD_RUNS_KEY, _records_adapter.dump_python(records, by_alias=True, mode='json')
            )
