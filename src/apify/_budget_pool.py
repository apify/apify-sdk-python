from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from logging import getLogger
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic.alias_generators import to_camel

from apify_client._models import PayPerEventActorPricingInfo as ClientPayPerEvent

from apify._utils import docs_group

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from apify_client import ApifyClientAsync
    from apify_client._models import Run

    from apify.storages import KeyValueStore

logger = getLogger(__name__)

DEFAULT_BUDGET_POOL_ALIAS = 'apify-budget-pool'
"""Alias of the key-value store holding the default budget pool of an Actor run."""

BUDGET_POOL_POLL_INTERVAL = timedelta(seconds=5)
"""How often the charges of running child runs are polled and written to their budget pools."""

_LIMIT_KEY = 'LIMIT'
_RUN_KEY_PREFIX = 'RUN-'

_TERMINAL_RUN_STATUSES = frozenset({'SUCCEEDED', 'FAILED', 'TIMED-OUT', 'ABORTED'})

BudgetPoolRunStatus = Literal['RUNNING', 'FINISHED']
"""Status of an orchestrating run as recorded in a budget pool."""

BudgetPoolChildStatus = Literal['RUNNING', 'FINISHED', 'ABORTED_BY_POOL']
"""Status of a child run as recorded in a budget pool."""


@docs_group('Charging')
class BudgetExhaustedError(RuntimeError):
    """Raised when a budget pool has no budget left for another child run."""


@docs_group('Charging')
class BudgetPoolNestingError(RuntimeError):
    """Raised when a run opens a budget pool in which it is already recorded as the child of another run.

    Its charges already count against the pool through its parent's record, so writing its own record would count
    them twice. A nested orchestrator should use its own pool instead.
    """


def _now() -> datetime:
    return datetime.now(UTC)


@docs_group('Charging')
class BudgetPoolChild(BaseModel):
    """A child run as recorded by the run that started it."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    actor_id: str | None = None
    """ID of the Actor of the child run."""

    max_charge_usd: Decimal | None = None
    """The `max_total_charge_usd` the child run was started with. `None` if unlimited."""

    charged_usd: Decimal = Decimal(0)
    """The amount the child run had charged when last polled. It includes the costs of runs it started itself."""

    status: BudgetPoolChildStatus = 'RUNNING'
    """Status of the child run when last polled."""

    updated_at: datetime = Field(default_factory=_now)
    """When the child run was last polled."""


@docs_group('Charging')
class BudgetPoolRunRecord(BaseModel):
    """The record of one orchestrating run in a budget pool - its own charges and those of its child runs.

    Only the run itself ever writes its record.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    run_id: str
    """ID of the orchestrating run."""

    status: BudgetPoolRunStatus = 'RUNNING'
    """Whether the orchestrating run is still running, and so still polls its child runs."""

    own_charged_usd: Decimal = Decimal(0)
    """The amount the orchestrating run has charged by itself."""

    children: dict[str, BudgetPoolChild] = Field(default_factory=dict)
    """Child runs started by the orchestrating run, keyed by run ID."""

    updated_at: datetime = Field(default_factory=_now)
    """When the record was last written."""

    def get_child_charged_usd(self, child: BudgetPoolChild) -> Decimal:
        """Return the amount a child run counts against the pool.

        A child still running after its orchestrating run finished is no longer polled, so it counts at the most it
        may charge - its `max_charge_usd` - unless it was seen charging more already.
        """
        if self.status == 'FINISHED' and child.status == 'RUNNING' and child.max_charge_usd is not None:
            return max(child.charged_usd, child.max_charge_usd)
        return child.charged_usd

    @property
    def charged_usd(self) -> Decimal:
        """The amount the orchestrating run and its child runs count against the pool."""
        return self.own_charged_usd + sum(
            (self.get_child_charged_usd(child) for child in self.children.values()), start=Decimal(0)
        )

    @property
    def unwatched_children(self) -> list[str]:
        """IDs of child runs still running after the orchestrating run finished, so nobody polls them."""
        if self.status != 'FINISHED':
            return []
        return [run_id for run_id, child in self.children.items() if child.status == 'RUNNING']


@docs_group('Charging')
class BudgetPool:
    """A charge budget shared by Actor runs, persisted in a key-value store.

    Every orchestrating run using the pool keeps one record in it, `RUN-<run ID>`, with its own charges and the
    charges of the child runs it started. A run writes only its own record, and nobody else ever does, so runs
    sharing a pool never overwrite each other and no locking is needed. The pool's charges are the sum of all
    records, and its limit is stored in the `LIMIT` record.

    Child runs are recorded by the run that started them, not by themselves: the orchestrating run polls its
    running children through the Apify API every `BUDGET_POOL_POLL_INTERVAL` and writes what it sees. A child's
    charges include those of the runs it started, so a nested orchestrator must not write into its parent's pool -
    it keeps its own pool, limited by the `max_total_charge_usd` its parent gave it. Opening a pool in which the run
    is already recorded as a child raises `BudgetPoolNestingError`.

    Charges are only known when polled, so the limit is not a hard one: the pool can overshoot it by what the
    children spend between two polls, plus the delay with which the Apify API reports charges.

    When an orchestrating run finishes while some of its children still run, nobody polls them any more. They then
    count at their `max_total_charge_usd`, the most they may charge, or at their last seen charges if those are
    higher. Children started without a limit count at their last seen charges only. If the orchestrating run is
    resurrected, it picks its record up again and resumes polling them.

    Use `Actor.open_budget_pool` to open a pool.
    """

    def __init__(self, key_value_store: KeyValueStore, *, owner_run_id: str, limit_usd: Decimal | None = None) -> None:
        """Create a new instance. Use `Actor.open_budget_pool` instead.

        Args:
            key_value_store: The key-value store holding the pool. It should not be used for anything else.
            owner_run_id: ID of the run using the pool. It writes only its own record.
            limit_usd: The total budget of the pool. If `None`, the limit stored in the pool is used.
        """
        self._key_value_store = key_value_store
        self._owner_run_id = owner_run_id
        self._limit_usd = limit_usd
        self._stored_limit_usd: Decimal | None = None
        self._own_record = BudgetPoolRunRecord(run_id=owner_run_id)
        self._other_records: dict[str, BudgetPoolRunRecord] = {}
        self._is_dirty = False

    @classmethod
    async def open(
        cls,
        key_value_store: KeyValueStore,
        *,
        owner_run_id: str,
        limit_usd: Decimal | None = None,
    ) -> BudgetPool:
        """Open a budget pool stored in the given key-value store. Use `Actor.open_budget_pool` instead.

        Args:
            key_value_store: The key-value store holding the pool. It should not be used for anything else.
            owner_run_id: ID of the run using the pool. It writes only its own record.
            limit_usd: The total budget of the pool. If set and different from the stored limit, it is stored.

        Raises:
            BudgetPoolNestingError: If the run is recorded in the pool as the child of another run.
        """
        pool = cls(key_value_store, owner_run_id=owner_run_id, limit_usd=limit_usd)

        stored = await key_value_store.get_value(pool._own_key)
        if stored is not None:
            # The run was restarted, migrated or resurrected - continue with its record.
            pool._own_record = BudgetPoolRunRecord.model_validate(stored)
            pool._own_record.status = 'RUNNING'

        await pool.refresh()

        parents = [record.run_id for record in pool._other_records.values() if owner_run_id in record.children]
        if parents:
            raise BudgetPoolNestingError(
                f'Run {owner_run_id} is recorded in this budget pool as a child of run {parents[0]}, which already '
                'counts its charges. Use a separate budget pool for it.'
            )

        if limit_usd is not None and limit_usd != pool._stored_limit_usd:
            await key_value_store.set_value(_LIMIT_KEY, {'limitUsd': str(limit_usd)})
            pool._stored_limit_usd = limit_usd

        await pool._save()
        return pool

    @property
    def limit_usd(self) -> Decimal:
        """The total budget of the pool, `Decimal('inf')` for an unlimited pool."""
        limit_usd = self._limit_usd if self._limit_usd is not None else self._stored_limit_usd
        return limit_usd if limit_usd is not None else Decimal('inf')

    @property
    def owner_run_id(self) -> str:
        """ID of the run using this pool instance."""
        return self._owner_run_id

    def get_records(self) -> dict[str, BudgetPoolRunRecord]:
        """Return the records of all orchestrating runs in the pool, keyed by run ID, as last read.

        Call `refresh` first to read the latest records of other runs.
        """
        records = {run_id: record.model_copy(deep=True) for run_id, record in self._other_records.items()}
        records[self._owner_run_id] = self._own_record.model_copy(deep=True)
        return records

    def get_charged_usd(self) -> Decimal:
        """Return the total amount charged against the pool, as last read."""
        return self._own_record.charged_usd + sum(
            (record.charged_usd for record in self._other_records.values()), start=Decimal(0)
        )

    def get_remaining_usd(self) -> Decimal:
        """Return the part of the limit not charged yet, as last read."""
        return max(Decimal(0), self.limit_usd - self.get_charged_usd())

    def is_exceeded(self) -> bool:
        """Return whether the charges in the pool exceed its limit, as last read."""
        return self.get_charged_usd() > self.limit_usd

    async def refresh(self) -> None:
        """Read the latest records of other runs and the limit from the key-value store."""
        run_keys: list[str] = []
        has_limit = False
        async for record_metadata in self._key_value_store.iterate_keys():
            key = record_metadata.key
            if key == _LIMIT_KEY:
                has_limit = True
            elif key.startswith(_RUN_KEY_PREFIX) and key != self._own_key:
                run_keys.append(key)

        values = await asyncio.gather(*(self._key_value_store.get_value(key) for key in run_keys))

        other_records: dict[str, BudgetPoolRunRecord] = {}
        for key, value in zip(run_keys, values, strict=True):
            if value is None:
                continue
            try:
                record = BudgetPoolRunRecord.model_validate(value)
            except ValidationError as exc:
                logger.warning(f'Ignoring an invalid budget pool record {key!r}: {exc}')
                continue
            other_records[record.run_id] = record
        self._other_records = other_records

        if has_limit:
            stored_limit = await self._key_value_store.get_value(_LIMIT_KEY)
            with suppress(InvalidOperation, TypeError, KeyError):
                self._stored_limit_usd = Decimal(str(stored_limit['limitUsd'])) if stored_limit else None

    # Updates of the own record - driven by `BudgetTracker`.

    @property
    def _own_key(self) -> str:
        return f'{_RUN_KEY_PREFIX}{self._owner_run_id}'

    def _get_child(self, run_id: str) -> BudgetPoolChild | None:
        return self._own_record.children.get(run_id)

    def _get_running_children(self) -> list[str]:
        return [run_id for run_id, child in self._own_record.children.items() if child.status == 'RUNNING']

    def _set_own_charged_usd(self, charged_usd: Decimal) -> None:
        if charged_usd > self._own_record.own_charged_usd:
            self._own_record.own_charged_usd = charged_usd
            self._is_dirty = True

    def _set_child(self, run_id: str, child: BudgetPoolChild) -> None:
        current = self._own_record.children.get(run_id)
        if current is not None and (current.charged_usd, current.status) == (child.charged_usd, child.status):
            return
        self._own_record.children[run_id] = child
        self._is_dirty = True

    def _set_status(self, status: BudgetPoolRunStatus) -> None:
        if self._own_record.status != status:
            self._own_record.status = status
            self._is_dirty = True

    async def _save(self, *, only_if_changed: bool = False) -> None:
        if only_if_changed and not self._is_dirty:
            return
        self._own_record.updated_at = _now()
        await self._key_value_store.set_value(self._own_key, self._own_record.model_dump(mode='json', by_alias=True))
        self._is_dirty = False


class BudgetTracker:
    """Polls the child runs of an Actor run and records their charges in the budget pools they belong to.

    It also records the run's own charges in every pool the run uses, and aborts child runs once a pool they belong
    to exceeds its limit, or once a child charges more than its own `max_total_charge_usd`. Meant to be instantiated
    internally by the `Actor` only.
    """

    def __init__(
        self,
        client: ApifyClientAsync,
        get_own_charged_usd: Callable[[], Decimal],
        *,
        poll_interval: timedelta = BUDGET_POOL_POLL_INTERVAL,
    ) -> None:
        self._client = client
        self._get_own_charged_usd = get_own_charged_usd
        self._poll_interval = poll_interval
        self._pools: list[BudgetPool] = []
        self._lock = asyncio.Lock()
        self._watch_task: asyncio.Task[None] | None = None

    async def add_pool(self, pool: BudgetPool) -> None:
        """Record the run's own charges in the pool from now on, and resume polling the children it lists."""
        if pool in self._pools:
            return
        async with self._lock:
            self._pools.append(pool)
            pool._set_own_charged_usd(self._get_own_charged_usd())  # noqa: SLF001
            pool._set_status('RUNNING')  # noqa: SLF001
            await pool._save(only_if_changed=True)  # noqa: SLF001
        if self._get_running_children():
            self._start_watching()

    async def allocate(self, pools: Iterable[BudgetPool], amount_usd: Decimal | None) -> Decimal | None:
        """Return the `max_total_charge_usd` for a child run about to start, capped at every pool's remaining budget.

        Returns:
            The amount, or `None` if the request and all the pools are unlimited.

        Raises:
            BudgetExhaustedError: If one of the pools has no budget left.
        """
        pools = list(pools)
        async with self._lock:
            await self._update(pools)

        granted = amount_usd if amount_usd is not None else Decimal('inf')
        for pool in pools:
            remaining = pool.get_remaining_usd()
            if remaining <= 0 and granted > 0:
                raise BudgetExhaustedError(
                    f'The budget pool has no budget left (limit {pool.limit_usd} USD, '
                    f'charged {pool.get_charged_usd()} USD).'
                )
            granted = min(granted, remaining)

        if amount_usd is not None and granted < amount_usd:
            logger.info(f'Requested budget of {amount_usd} USD capped at the remaining {granted} USD.')
        return granted if granted.is_finite() else None

    async def track(self, pools: Iterable[BudgetPool], run: Run, max_charge_usd: Decimal | None) -> None:
        """Record a child run that has just started in the given pools, and keep polling it while it runs."""
        child = BudgetPoolChild(
            actor_id=run.act_id,
            max_charge_usd=max_charge_usd,
            charged_usd=get_run_charged_usd(run),
            status='FINISHED' if run.status in _TERMINAL_RUN_STATUSES else 'RUNNING',
        )
        async with self._lock:
            for pool in pools:
                pool._set_child(run.id, child)  # noqa: SLF001
                await pool._save(only_if_changed=True)  # noqa: SLF001
        self._start_watching()

    async def update(self, run: Run) -> None:
        """Record the latest state of a child run, e.g. once it finished."""
        async with self._lock:
            self._apply_run(run)
            for pool in self._pools:
                await pool._save(only_if_changed=True)  # noqa: SLF001

    async def poll(self) -> list[str]:
        """Poll the running children, record their charges, and abort those over a budget.

        Returns:
            IDs of the child runs that were aborted.
        """
        async with self._lock:
            await self._update(self._pools)
            aborted = await self._enforce()
            for pool in self._pools:
                await pool._save(only_if_changed=True)  # noqa: SLF001
            return aborted

    async def close(self) -> None:
        """Record the final charges of the children, and mark the run as finished in its pools."""
        await self._stop_watching()
        async with self._lock:
            try:
                await self._update(self._pools, refresh=False)
            finally:
                for pool in self._pools:
                    pool._set_status('FINISHED')  # noqa: SLF001
                    await pool._save(only_if_changed=True)  # noqa: SLF001

        unwatched = self._get_running_children()
        if unwatched:
            logger.warning(
                f'{len(unwatched)} child run(s) are still running and will no longer be polled. Until this run is '
                'resurrected, they count against their budget pools at their max_total_charge_usd.'
            )

    def _get_running_children(self) -> set[str]:
        return {run_id for pool in self._pools for run_id in pool._get_running_children()}  # noqa: SLF001

    def _apply_run(self, run: Run, *, status: BudgetPoolChildStatus | None = None) -> None:
        charged_usd = get_run_charged_usd(run)
        for pool in self._pools:
            current = pool._get_child(run.id)  # noqa: SLF001
            if current is None:
                continue
            new_status = status or current.status
            if new_status == 'RUNNING' and run.status in _TERMINAL_RUN_STATUSES:
                new_status = 'FINISHED'
            pool._set_child(  # noqa: SLF001
                run.id,
                current.model_copy(
                    update={
                        'charged_usd': max(current.charged_usd, charged_usd),
                        'status': new_status,
                        'updated_at': _now(),
                    }
                ),
            )

    async def _update(self, pools: list[BudgetPool], *, refresh: bool = True) -> None:
        own_charged_usd = self._get_own_charged_usd()
        for pool in self._pools:
            pool._set_own_charged_usd(own_charged_usd)  # noqa: SLF001

        running = sorted(self._get_running_children())
        runs = await asyncio.gather(*(self._client.run(run_id).get() for run_id in running), return_exceptions=True)
        for run_id, run in zip(running, runs, strict=True):
            if isinstance(run, BaseException):
                logger.warning(f'Failed to poll the charges of run {run_id}: {run}')
            elif run is not None:
                self._apply_run(run)

        for pool in self._pools:
            await pool._save(only_if_changed=True)  # noqa: SLF001

        if refresh:
            await asyncio.gather(*(pool.refresh() for pool in pools))

    async def _enforce(self) -> list[str]:
        reasons: dict[str, str] = {}
        for pool in self._pools:
            is_exceeded = pool.is_exceeded()
            for run_id in pool._get_running_children():  # noqa: SLF001
                child = pool._get_child(run_id)  # noqa: SLF001
                if child is None or run_id in reasons:
                    continue
                if is_exceeded:
                    reasons[run_id] = (
                        f'the budget pool charges ({pool.get_charged_usd()} USD) exceed '
                        f'its limit ({pool.limit_usd} USD)'
                    )
                elif child.max_charge_usd is not None and child.charged_usd > child.max_charge_usd:
                    reasons[run_id] = (
                        f'it charged {child.charged_usd} USD, more than its max_total_charge_usd of '
                        f'{child.max_charge_usd} USD'
                    )

        aborted: list[str] = []
        for run_id, reason in reasons.items():
            logger.warning(f'Aborting child run {run_id}: {reason}.')
            try:
                run = await self._client.run(run_id).abort()
            except Exception as exc:
                logger.warning(f'Failed to abort run {run_id}: {exc}')
                continue
            self._apply_run(run, status='ABORTED_BY_POOL')
            aborted.append(run_id)
        return aborted

    def _start_watching(self) -> None:
        if self._watch_task is not None and not self._watch_task.done():
            return
        self._watch_task = asyncio.create_task(self._watch(), name='budget-pool-watcher')

    async def _stop_watching(self) -> None:
        task, self._watch_task = self._watch_task, None
        if task is None or task.done():
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def _watch(self) -> None:
        while self._get_running_children():
            await asyncio.sleep(self._poll_interval.total_seconds())
            try:
                await self.poll()
            except Exception:
                logger.exception('Failed to poll the charges of child runs')


def get_run_charged_usd(run: Run) -> Decimal:
    """Compute the amount a run has charged - the amount its `max_total_charge_usd` limits.

    For pay-per-event runs this is the sum of the charged events multiplied by their prices. For other runs, or when
    some event price is not known, the run's `usage_total_usd` is used instead.
    """
    usage_total_usd = Decimal(str(run.usage_total_usd)) if run.usage_total_usd is not None else Decimal(0)

    pricing_info = run.pricing_info
    if not isinstance(pricing_info, ClientPayPerEvent):
        return usage_total_usd

    charge_events = pricing_info.pricing_per_event.actor_charge_events or {}
    total = Decimal(0)
    for event_name, count in (run.charged_event_counts or {}).items():
        event = charge_events.get(event_name)
        if event is None or event.event_price_usd is None:
            # Tier-priced or unknown event - its price cannot be computed here.
            return usage_total_usd
        total += Decimal(str(event.event_price_usd)) * count
    return total
