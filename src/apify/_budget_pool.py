from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from logging import getLogger
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from apify_client._models import PayPerEventActorPricingInfo as ClientPayPerEvent
from crawlee._utils.crypto import crypto_random_object_id

from apify._utils import docs_group

if TYPE_CHECKING:
    from collections.abc import Callable

    from apify_client import ApifyClientAsync
    from apify_client._models import Run

    from apify.storages import KeyValueStore

logger = getLogger(__name__)

DEFAULT_BUDGET_POOL_KEY = 'APIFY_BUDGET_POOL'
"""Key-value store record under which a budget pool is persisted by default."""

BUDGET_POOL_POLL_INTERVAL = timedelta(seconds=5)
"""How often a budget pool polls its running child runs for their charges by default."""

BUDGET_POOL_OVERSHOOT_TOLERANCE = Decimal('0.05')
"""By how much, as a fraction of the limit, the charges in a budget pool may exceed the limit by default before the
pool aborts its running child runs. Charges are polled, so a small overshoot cannot be avoided."""

_TERMINAL_RUN_STATUSES = frozenset({'SUCCEEDED', 'FAILED', 'TIMED-OUT', 'ABORTED'})


@docs_group('Charging')
class BudgetExhaustedError(RuntimeError):
    """Raised when a budget pool has no budget left for another child run."""


@docs_group('Charging')
class BudgetPoolEntry(BaseModel):
    """A single run charging against a budget pool - a child run, or a run's own charges."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    run_id: str | None = None
    """ID of the run this entry belongs to, if known. An allocation has no run until the run is started."""

    actor_id: str | None = None
    """ID of the Actor whose run this entry belongs to, if known."""

    label: str | None = None
    """Optional human-readable description of the entry."""

    is_child_run: bool = True
    """Whether the entry tracks a child run started through the pool, as opposed to charges recorded by a run itself
    via `BudgetPool.record_charges`. Only child runs are polled from the Apify API."""

    max_charge_usd: Decimal | None = None
    """The `max_total_charge_usd` the run was started with. `None` if unlimited."""

    charged_usd: Decimal = Decimal(0)
    """Amount the run has charged so far, as last observed."""

    is_finished: bool = False
    """Whether the run has finished."""

    is_aborted_by_pool: bool = False
    """Whether the pool aborted the run because the budget was exceeded."""

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    """When the entry was created."""

    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    """When the charges of the entry were last updated."""


@docs_group('Charging')
@dataclass(frozen=True)
class BudgetAllocation:
    """Result of `BudgetPool.allocate` - the budget a child run is about to be started with."""

    id: str
    """ID of the pool entry tracking the child run."""

    amount_usd: Decimal
    """The allocated amount - pass it to the child run as `max_total_charge_usd`. Infinite for an unlimited pool."""


class _BudgetPoolState(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    limit_usd: Decimal | None = None
    entries: dict[str, BudgetPoolEntry] = Field(default_factory=dict)


@docs_group('Charging')
class BudgetPool:
    """A charge budget shared by several Actor runs, persisted in a key-value store record.

    Every run in the pool charges against it continuously: while child runs are running, the pool polls their
    charges (every `BUDGET_POOL_POLL_INTERVAL` by default) and records them, so the remaining budget reflects what
    has been spent so far, not only what finished runs spent.

    A child run started through the pool gets the budget remaining at that moment as its `max_total_charge_usd`,
    which the platform enforces for pay-per-event Actors. Children running at the same time share the remaining
    budget, so together they can spend more than is left. When the charges in the pool exceed the limit by more
    than the overshoot tolerance, the pool aborts all its running child runs. A child that charges more than its own
    `max_total_charge_usd` by more than the tolerance - possible for Actors using another pricing model, or for
    orchestrators that do not limit their own children - is aborted too. Because charges are polled, the pool can
    overshoot its limit by what the children spend between two polls.

    The pool also serves as a cost record: `get_entries` lists every run that charged against it and by how much.

    The state lives in a key-value store, so it survives migrations and restarts when kept in the run's default
    store, can be shared by unrelated Actor runs when kept in a named store, and works locally as well. Operations
    within one process are serialized. Runs sharing a pool through a named store read and write the record without
    any cross-process locking, so concurrent updates from different runs are best-effort.

    Use `Actor.open_budget_pool` to open a pool. When the Actor run has `max_total_charge_usd` set and uses the
    pay-per-event pricing model, `Actor.start` and `Actor.call` use a default pool limited to that amount.
    """

    def __init__(
        self,
        key_value_store: KeyValueStore,
        *,
        key: str = DEFAULT_BUDGET_POOL_KEY,
        limit_usd: Decimal | None = None,
        default_child_budget_usd: Decimal | None = None,
        overshoot_tolerance: Decimal = BUDGET_POOL_OVERSHOOT_TOLERANCE,
        client: ApifyClientAsync | None = None,
        poll_interval: timedelta | None = BUDGET_POOL_POLL_INTERVAL,
    ) -> None:
        """Create a new instance. Prefer `Actor.open_budget_pool`, which also loads the stored state.

        Args:
            key_value_store: The key-value store holding the pool state.
            key: The record key under which the pool state is stored.
            limit_usd: The total budget of the pool. If `None`, the limit stored in the record is used, and if
                there is none, the pool is unlimited and only tracks costs.
            default_child_budget_usd: The `max_total_charge_usd` of a child run started without one, capped at
                the remaining budget. If `None`, such a child gets the whole remaining budget.
            overshoot_tolerance: By how much, as a fraction of the limit, the charges may exceed the limit before
                the running child runs are aborted. The same fraction of a child's own `max_total_charge_usd`
                applies to a single child.
            client: The Apify API client used to poll the tracked child runs and to abort them.
            poll_interval: How often the background watcher started by `start_watching` polls the running child
                runs. `None` disables the watcher, and with it aborting the children.
        """
        if overshoot_tolerance < 0:
            raise ValueError(f'The overshoot tolerance must not be negative, got {overshoot_tolerance}.')

        self._key_value_store = key_value_store
        self._key = key
        self._limit_usd = limit_usd
        self._default_child_budget_usd = default_child_budget_usd
        self._overshoot_tolerance = overshoot_tolerance
        self._client = client
        self._poll_interval = poll_interval
        self._state = _BudgetPoolState(limit_usd=limit_usd)
        self._lock = asyncio.Lock()
        self._watch_task: asyncio.Task[None] | None = None
        self._charge_sources: dict[str, tuple[Callable[[], Decimal], str | None]] = {}

    @classmethod
    async def open(
        cls,
        key_value_store: KeyValueStore,
        *,
        key: str = DEFAULT_BUDGET_POOL_KEY,
        limit_usd: Decimal | None = None,
        default_child_budget_usd: Decimal | None = None,
        overshoot_tolerance: Decimal = BUDGET_POOL_OVERSHOOT_TOLERANCE,
        client: ApifyClientAsync | None = None,
        poll_interval: timedelta | None = BUDGET_POOL_POLL_INTERVAL,
    ) -> BudgetPool:
        """Open a budget pool stored in the given key-value store, creating the record if it does not exist.

        Args:
            key_value_store: The key-value store holding the pool state.
            key: The record key under which the pool state is stored.
            limit_usd: The total budget of the pool. Overrides the limit stored in the record, if any.
            default_child_budget_usd: The `max_total_charge_usd` of a child run started without one, capped at
                the remaining budget.
            overshoot_tolerance: By how much, as a fraction of the limit, the charges may exceed the limit before
                the running child runs are aborted.
            client: The Apify API client used to poll the tracked child runs and to abort them.
            poll_interval: How often the background watcher polls the running child runs. `None` disables it.
        """
        pool = cls(
            key_value_store,
            key=key,
            limit_usd=limit_usd,
            default_child_budget_usd=default_child_budget_usd,
            overshoot_tolerance=overshoot_tolerance,
            client=client,
            poll_interval=poll_interval,
        )
        async with pool._lock:
            await pool._load()
            await pool._save()
        return pool

    @property
    def limit_usd(self) -> Decimal:
        """The total budget of the pool, `Decimal('inf')` for an unlimited pool."""
        return self._state.limit_usd if self._state.limit_usd is not None else Decimal('inf')

    @property
    def default_child_budget_usd(self) -> Decimal | None:
        """The `max_total_charge_usd` of a child run started without one."""
        return self._default_child_budget_usd

    @property
    def overshoot_tolerance(self) -> Decimal:
        """By how much, as a fraction of the limit, the charges may exceed the limit before children are aborted."""
        return self._overshoot_tolerance

    async def get_entries(self) -> dict[str, BudgetPoolEntry]:
        """Return the entries of the pool, keyed by entry ID, as currently stored."""
        async with self._lock:
            await self._load()
            return {entry_id: entry.model_copy() for entry_id, entry in self._state.entries.items()}

    async def get_charged_usd(self) -> Decimal:
        """Return the total amount charged against the pool so far, as currently stored."""
        async with self._lock:
            await self._load()
            return self._charged_usd()

    async def get_remaining_usd(self, *, refresh: bool = True) -> Decimal:
        """Return the part of the limit not charged yet.

        Args:
            refresh: Whether to first poll the running child runs for their current charges.
        """
        async with self._lock:
            await self._load()
            if refresh and await self._refresh():
                await self._save()
            return self._remaining_usd()

    async def refresh(self) -> None:
        """Poll the running child runs for their current charges and record them."""
        async with self._lock:
            await self._load()
            if await self._refresh():
                await self._save()

    async def allocate(
        self,
        amount_usd: Decimal | None = None,
        *,
        actor_id: str | None = None,
        label: str | None = None,
    ) -> BudgetAllocation:
        """Decide the `max_total_charge_usd` of a child run about to be started, and start tracking it.

        The running child runs are polled first, so the remaining budget is current.

        Args:
            amount_usd: The requested amount. It is capped at the remaining budget. If `None`, the pool's
                `default_child_budget_usd` is requested, or the whole remaining budget if that is not set either.
            actor_id: ID of the Actor the child run belongs to, stored for reference.
            label: Optional human-readable description of the child run.

        Returns:
            The allocation. Its `amount_usd` is infinite if both the pool and the request are unlimited.

        Raises:
            BudgetExhaustedError: If there is no budget left.
        """
        if amount_usd is not None and amount_usd < 0:
            raise ValueError(f'The allocated amount must not be negative, got {amount_usd}.')

        async with self._lock:
            await self._load()
            await self._refresh()

            remaining = self._remaining_usd()
            requested = amount_usd if amount_usd is not None else self._default_child_budget_usd

            if remaining <= 0 and (requested is None or requested > 0):
                await self._save()
                raise BudgetExhaustedError(
                    f'The budget pool has no budget left (limit {self.limit_usd} USD, '
                    f'charged {self._charged_usd()} USD).'
                )

            granted = remaining if requested is None else min(requested, remaining)
            if requested is not None and granted < requested:
                logger.info(f'Requested budget of {requested} USD capped at the remaining {granted} USD.')

            entry_id = crypto_random_object_id()
            self._state.entries[entry_id] = BudgetPoolEntry(
                actor_id=actor_id,
                label=label,
                max_charge_usd=granted if granted.is_finite() else None,
            )
            await self._save()

        return BudgetAllocation(id=entry_id, amount_usd=granted)

    async def release(self, allocation_id: str) -> None:
        """Drop an allocation whose child run was not started, e.g. because starting it failed.

        Args:
            allocation_id: ID of the allocation, as returned by `allocate`.
        """
        async with self._lock:
            await self._load()
            if self._state.entries.pop(allocation_id, None) is not None:
                await self._save()

    async def track_run(self, allocation_id: str, run: Run) -> None:
        """Associate an allocation with the child run started for it, and record the run's current charges.

        Args:
            allocation_id: ID of the allocation, as returned by `allocate`.
            run: The child run started with the allocated budget.
        """
        async with self._lock:
            await self._load()
            entry = self._state.entries.get(allocation_id)
            if entry is None:
                entry = BudgetPoolEntry()
                self._state.entries[allocation_id] = entry
            entry.run_id = run.id
            entry.actor_id = run.act_id
            self._apply_run(entry, run)
            await self._save()

    async def update_run(self, run: Run) -> None:
        """Record the current charges and status of a tracked child run, e.g. after it finished.

        Args:
            run: The latest state of the child run.
        """
        async with self._lock:
            await self._load()
            entry = self._find_run_entry(run.id)
            if entry is None:
                entry = BudgetPoolEntry(run_id=run.id, actor_id=run.act_id)
                self._state.entries[run.id] = entry
            self._apply_run(entry, run)
            await self._save()

    async def record_charges(self, run_id: str, charged_usd: Decimal, *, label: str | None = None) -> None:
        """Record the amount a run has charged by itself so far, e.g. the orchestrating run's own charges.

        If the run is already tracked in the pool (for instance as a child of another run sharing the pool), its
        existing entry is updated, so the charges are not counted twice.

        Args:
            run_id: ID of the run.
            charged_usd: The total amount the run has charged so far.
            label: Optional human-readable description of the entry.
        """
        async with self._lock:
            await self._load()
            if self._record_charges(run_id, charged_usd, label):
                await self._save()

    def track_charges(self, run_id: str, get_charged_usd: Callable[[], Decimal], *, label: str | None = None) -> None:
        """Keep recording a run's own charges on every poll, e.g. the charges of the orchestrating run itself.

        Args:
            run_id: ID of the run.
            get_charged_usd: Returns the total amount the run has charged so far.
            label: Optional human-readable description of the entry.
        """
        self._charge_sources[run_id] = (get_charged_usd, label)

    async def enforce(self) -> list[str]:
        """Poll the running child runs and abort them if the budget is exceeded beyond the overshoot tolerance.

        All running children are aborted when the charges in the pool exceed the limit by more than the tolerance.
        A single child is aborted when it charged more than its own `max_total_charge_usd` by more than the
        tolerance.

        Returns:
            IDs of the runs that were aborted.
        """
        async with self._lock:
            await self._load()
            changed = await self._refresh()

            running = [
                entry
                for entry in self._state.entries.values()
                if entry.is_child_run and entry.run_id is not None and not entry.is_finished
            ]

            charged = self._charged_usd()
            is_pool_exceeded = charged > self.limit_usd * (1 + self._overshoot_tolerance)
            if is_pool_exceeded and running:
                logger.warning(
                    f'The budget pool charges ({charged} USD) exceed its limit ({self.limit_usd} USD) beyond the '
                    f'tolerance, aborting {len(running)} running child run(s).'
                )

            to_abort = [entry for entry in running if is_pool_exceeded or self._is_over_own_limit(entry)]

            aborted: list[str] = []
            if to_abort and self._client is not None:
                for entry in to_abort:
                    if entry.run_id is None:
                        continue
                    if not is_pool_exceeded:
                        logger.warning(
                            f'Aborting run {entry.run_id}: it charged {entry.charged_usd} USD, beyond its '
                            f'max_total_charge_usd of {entry.max_charge_usd} USD.'
                        )
                    try:
                        run = await self._client.run(entry.run_id).abort()
                    except Exception as exc:
                        logger.warning(f'Failed to abort run {entry.run_id}: {exc}')
                        continue
                    entry.is_aborted_by_pool = True
                    self._apply_run(entry, run)
                    aborted.append(entry.run_id)
                    changed = True

            if changed:
                await self._save()

            return aborted

    def start_watching(self) -> None:
        """Start a background task that calls `enforce` every poll interval while there are running child runs.

        The task stops by itself once all tracked child runs finish, and calling this again restarts it. It does
        nothing if the watcher is disabled or already running.
        """
        if self._poll_interval is None or self._client is None:
            return
        if self._watch_task is not None and not self._watch_task.done():
            return
        self._watch_task = asyncio.create_task(self._watch(self._poll_interval), name='budget-pool-watcher')

    async def stop_watching(self) -> None:
        """Stop the background task started by `start_watching`, if it is running."""
        task, self._watch_task = self._watch_task, None
        if task is None or task.done():
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def _watch(self, interval: timedelta) -> None:
        while True:
            await asyncio.sleep(interval.total_seconds())
            try:
                await self.enforce()
            except Exception:
                logger.exception('Failed to check the charges of child runs in the budget pool')
            if not self._has_running_child_runs():
                return

    def _has_running_child_runs(self) -> bool:
        return any(
            entry.is_child_run and entry.run_id is not None and not entry.is_finished
            for entry in self._state.entries.values()
        )

    def _is_over_own_limit(self, entry: BudgetPoolEntry) -> bool:
        return entry.max_charge_usd is not None and entry.charged_usd > entry.max_charge_usd * (
            1 + self._overshoot_tolerance
        )

    def _charged_usd(self) -> Decimal:
        return sum((entry.charged_usd for entry in self._state.entries.values()), start=Decimal(0))

    def _remaining_usd(self) -> Decimal:
        return max(Decimal(0), self.limit_usd - self._charged_usd())

    def _find_run_entry(self, run_id: str) -> BudgetPoolEntry | None:
        entry = self._state.entries.get(run_id)
        if entry is not None:
            return entry
        return next((entry for entry in self._state.entries.values() if entry.run_id == run_id), None)

    def _record_charges(self, run_id: str, charged_usd: Decimal, label: str | None) -> bool:
        entry = self._find_run_entry(run_id)
        if entry is None:
            entry = BudgetPoolEntry(run_id=run_id, label=label, is_child_run=False)
            self._state.entries[run_id] = entry
        elif entry.charged_usd == charged_usd:
            return False
        entry.charged_usd = charged_usd
        entry.updated_at = datetime.now(UTC)
        return True

    async def _refresh(self) -> bool:
        """Record the current charges of tracked runs. Returns whether anything changed."""
        changed = False
        for run_id, (get_charged_usd, label) in self._charge_sources.items():
            changed = self._record_charges(run_id, get_charged_usd(), label) or changed

        if self._client is None:
            return changed

        entries = [
            entry
            for entry in self._state.entries.values()
            if entry.is_child_run and entry.run_id is not None and not entry.is_finished
        ]
        if not entries:
            return changed

        runs = await asyncio.gather(
            *(self._client.run(entry.run_id).get() for entry in entries if entry.run_id is not None),
            return_exceptions=True,
        )

        for entry, run in zip(entries, runs, strict=True):
            if isinstance(run, BaseException):
                logger.warning(f'Failed to poll the charges of run {entry.run_id}: {run}')
                continue
            if run is None:
                continue
            before = (entry.charged_usd, entry.is_finished)
            self._apply_run(entry, run)
            changed = changed or before != (entry.charged_usd, entry.is_finished)
        return changed

    @staticmethod
    def _apply_run(entry: BudgetPoolEntry, run: Run) -> None:
        charged_usd = max(entry.charged_usd, get_run_charged_usd(run))
        if charged_usd != entry.charged_usd:
            entry.charged_usd = charged_usd
            entry.updated_at = datetime.now(UTC)
        entry.is_finished = run.status in _TERMINAL_RUN_STATUSES

    async def _load(self) -> None:
        stored = await self._key_value_store.get_value(self._key)
        state = _BudgetPoolState.model_validate(stored) if stored is not None else _BudgetPoolState()
        if self._limit_usd is not None:
            state.limit_usd = self._limit_usd
        self._state = state

    async def _save(self) -> None:
        await self._key_value_store.set_value(self._key, self._state.model_dump(mode='json', by_alias=True))


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
