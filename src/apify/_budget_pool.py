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
    from apify_client import ApifyClientAsync
    from apify_client._models import Run

    from apify.storages import KeyValueStore

logger = getLogger(__name__)

DEFAULT_BUDGET_POOL_KEY = 'APIFY_BUDGET_POOL'
"""Key-value store record under which a budget pool is persisted by default."""

_TERMINAL_RUN_STATUSES = frozenset({'SUCCEEDED', 'FAILED', 'TIMED-OUT', 'ABORTED'})


@docs_group('Charging')
class BudgetExhaustedError(RuntimeError):
    """Raised when a budget pool has no budget left for another reservation."""


@docs_group('Charging')
class BudgetPoolEntry(BaseModel):
    """A single contribution to a budget pool - a reservation for a child run, or a run's own charges."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    run_id: str | None = None
    """ID of the run this entry belongs to, if known. A reservation has no run until the run is started."""

    actor_id: str | None = None
    """ID of the Actor whose run this entry belongs to, if known."""

    label: str | None = None
    """Optional human-readable description of the entry."""

    is_child_run: bool = True
    """Whether the entry tracks a child run started through the pool, as opposed to charges recorded by a run itself
    via `BudgetPool.record_charges`. Only child runs are refreshed from the Apify API."""

    reserved_usd: Decimal | None = Decimal(0)
    """Budget set aside for the run - the `max_total_charge_usd` it was started with. `None` if unlimited."""

    charged_usd: Decimal = Decimal(0)
    """Amount the run has charged so far, as last observed."""

    is_finished: bool = False
    """Whether the run has finished, so its unused reservation no longer counts against the pool."""

    is_aborted_by_pool: bool = False
    """Whether the pool aborted the run because it charged more than its reservation."""

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    """When the entry was created."""

    @property
    def committed_usd(self) -> Decimal:
        """Amount of the pool this entry currently takes up."""
        if self.is_finished or self.reserved_usd is None:
            return self.charged_usd
        return max(self.reserved_usd, self.charged_usd)

    @property
    def is_over_budget(self) -> bool:
        """Whether the run has charged more than its reservation."""
        return self.reserved_usd is not None and self.charged_usd > self.reserved_usd


@docs_group('Charging')
@dataclass(frozen=True)
class BudgetReservation:
    """Result of `BudgetPool.reserve` - a slice of the pool set aside for one child run."""

    id: str
    """ID of the pool entry holding the reservation."""

    amount_usd: Decimal
    """The reserved amount - pass it to the child run as `max_total_charge_usd`."""


class _BudgetPoolState(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    limit_usd: Decimal | None = None
    entries: dict[str, BudgetPoolEntry] = Field(default_factory=dict)


@docs_group('Charging')
class BudgetPool:
    """A charge budget shared by several Actor runs, persisted in a key-value store record.

    Every child run started through the pool gets a slice of the remaining budget reserved for it and is started
    with that slice as its `max_total_charge_usd`. Because the reservations of running children are counted
    against the pool, children running at the same time can never be granted more than the pool's limit in total.
    Once a child finishes, only what it actually charged stays counted, and the rest of its reservation returns to
    the pool.

    The platform stops a pay-per-event child once it reaches its `max_total_charge_usd`, but that limit does not
    cover everything - a child using another pricing model, or a child that starts its own children without
    reserving their budget, can cost more than its reservation. The pool therefore watches its unfinished child
    runs in the background and aborts any that charged more than was reserved for it, see `enforce`.

    The pool also serves as a cost record: `get_entries` lists every run that contributed and by how much.

    The state lives in a key-value store, so it survives migrations and restarts when kept in the run's default
    store, can be shared by unrelated Actor runs when kept in a named store, and works locally as well. Operations
    within one process are serialized. Runs sharing a pool through a named store read and write the record without
    any cross-process locking, so concurrent updates from different runs are best-effort. Charged amounts are read
    from the Apify API and may lag slightly behind the actual charges.

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
        client: ApifyClientAsync | None = None,
        watch_interval: timedelta | None = timedelta(seconds=30),
    ) -> None:
        """Create a new instance. Prefer `Actor.open_budget_pool`, which also loads the stored state.

        Args:
            key_value_store: The key-value store holding the pool state.
            key: The record key under which the pool state is stored.
            limit_usd: The total budget of the pool. If `None`, the limit stored in the record is used, and if
                there is none, the pool is unlimited and only tracks costs.
            default_child_budget_usd: Amount reserved for a child run started without an explicit
                `max_total_charge_usd`. If `None`, such a child gets the whole remaining budget, which leaves
                nothing for children started while it runs.
            client: The Apify API client used to read the charges of tracked child runs and to abort them.
            watch_interval: How often the background watcher started by `start_watching` checks the charges of
                unfinished child runs. `None` disables the watcher.
        """
        self._key_value_store = key_value_store
        self._key = key
        self._limit_usd = limit_usd
        self._default_child_budget_usd = default_child_budget_usd
        self._client = client
        self._state = _BudgetPoolState(limit_usd=limit_usd)
        self._lock = asyncio.Lock()
        self._watch_interval = watch_interval
        self._watch_task: asyncio.Task[None] | None = None

    @classmethod
    async def open(
        cls,
        key_value_store: KeyValueStore,
        *,
        key: str = DEFAULT_BUDGET_POOL_KEY,
        limit_usd: Decimal | None = None,
        default_child_budget_usd: Decimal | None = None,
        client: ApifyClientAsync | None = None,
        watch_interval: timedelta | None = timedelta(seconds=30),
    ) -> BudgetPool:
        """Open a budget pool stored in the given key-value store, creating the record if it does not exist.

        Args:
            key_value_store: The key-value store holding the pool state.
            key: The record key under which the pool state is stored.
            limit_usd: The total budget of the pool. Overrides the limit stored in the record, if any.
            default_child_budget_usd: Amount reserved for a child run started without an explicit
                `max_total_charge_usd`.
            client: The Apify API client used to read the charges of tracked child runs and to abort them.
            watch_interval: How often the background watcher started by `start_watching` checks the charges of
                unfinished child runs. `None` disables the watcher.
        """
        pool = cls(
            key_value_store,
            key=key,
            limit_usd=limit_usd,
            default_child_budget_usd=default_child_budget_usd,
            client=client,
            watch_interval=watch_interval,
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
        """Amount reserved for a child run started without an explicit `max_total_charge_usd`."""
        return self._default_child_budget_usd

    async def get_entries(self) -> dict[str, BudgetPoolEntry]:
        """Return the entries of the pool, keyed by entry ID, as currently stored."""
        async with self._lock:
            await self._load()
            return {entry_id: entry.model_copy() for entry_id, entry in self._state.entries.items()}

    async def get_charged_usd(self) -> Decimal:
        """Return the total amount charged by all runs tracked in the pool, as currently stored."""
        async with self._lock:
            await self._load()
            return sum((entry.charged_usd for entry in self._state.entries.values()), start=Decimal(0))

    async def get_remaining_usd(self, *, refresh: bool = True) -> Decimal:
        """Return the part of the limit that is neither charged nor reserved for a running child.

        Args:
            refresh: Whether to first update the charges of unfinished child runs from the Apify API.
        """
        async with self._lock:
            await self._load()
            if refresh and await self._refresh_runs():
                await self._save()
            return self._remaining_usd()

    async def refresh(self) -> None:
        """Update the charges and status of unfinished child runs from the Apify API."""
        async with self._lock:
            await self._load()
            if await self._refresh_runs():
                await self._save()

    async def reserve(
        self,
        amount_usd: Decimal | None = None,
        *,
        actor_id: str | None = None,
        label: str | None = None,
    ) -> BudgetReservation:
        """Set aside part of the remaining budget for a child run.

        The charges of unfinished child runs are refreshed first, so budget left unused by children that finished
        in the meantime is available again.

        Args:
            amount_usd: The requested amount. It is capped at the remaining budget. If `None`, the pool's
                `default_child_budget_usd` is requested, or the whole remaining budget if that is not set either.
            actor_id: ID of the Actor the reservation is for, stored for reference.
            label: Optional human-readable description of the reservation.

        Returns:
            The reservation. Its `amount_usd` is infinite if both the pool and the request are unlimited.

        Raises:
            BudgetExhaustedError: If there is no budget left.
        """
        if amount_usd is not None and amount_usd < 0:
            raise ValueError(f'The reserved amount must not be negative, got {amount_usd}.')

        async with self._lock:
            await self._load()
            await self._refresh_runs()

            remaining = self._remaining_usd()
            requested = amount_usd if amount_usd is not None else self._default_child_budget_usd
            granted = remaining if requested is None else min(requested, remaining)

            if remaining <= 0 and (requested is None or requested > 0):
                await self._save()
                raise BudgetExhaustedError(
                    f'The budget pool has no budget left (limit {self.limit_usd} USD, remaining {remaining} USD).'
                )

            if requested is not None and granted < requested:
                logger.info(f'Requested budget of {requested} USD capped at the remaining {granted} USD.')

            entry_id = crypto_random_object_id()
            self._state.entries[entry_id] = BudgetPoolEntry(
                actor_id=actor_id,
                label=label,
                reserved_usd=granted if granted.is_finite() else None,
            )
            await self._save()

        return BudgetReservation(id=entry_id, amount_usd=granted)

    async def release(self, reservation_id: str) -> None:
        """Drop a reservation that was not used, e.g. because starting the child run failed.

        Args:
            reservation_id: ID of the reservation, as returned by `reserve`.
        """
        async with self._lock:
            await self._load()
            if self._state.entries.pop(reservation_id, None) is not None:
                await self._save()

    async def track_run(self, reservation_id: str, run: Run) -> None:
        """Associate a reservation with the child run started for it, and record the run's current charges.

        Args:
            reservation_id: ID of the reservation, as returned by `reserve`.
            run: The child run started with the reserved budget.
        """
        async with self._lock:
            await self._load()
            entry = self._state.entries.get(reservation_id)
            if entry is None:
                entry = BudgetPoolEntry()
                self._state.entries[reservation_id] = entry
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
            entry = self._find_run_entry(run_id)
            if entry is None:
                entry = BudgetPoolEntry(run_id=run_id, label=label, is_child_run=False)
                self._state.entries[run_id] = entry
            if entry.charged_usd == charged_usd:
                return
            entry.charged_usd = charged_usd
            await self._save()

    async def enforce(self) -> list[str]:
        """Refresh the unfinished child runs and abort those that charged more than was reserved for them.

        Returns:
            IDs of the runs that were aborted.
        """
        async with self._lock:
            await self._load()
            changed = await self._refresh_runs()

            over_budget = [
                entry
                for entry in self._state.entries.values()
                if entry.is_child_run and entry.run_id is not None and not entry.is_finished and entry.is_over_budget
            ]

            aborted: list[str] = []
            if over_budget and self._client is not None:
                for entry in over_budget:
                    if entry.run_id is None:
                        continue
                    logger.warning(
                        f'Aborting run {entry.run_id}: it charged {entry.charged_usd} USD, '
                        f'more than the {entry.reserved_usd} USD reserved for it in the budget pool.'
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
        """Start a background task that periodically calls `enforce` while there are unfinished child runs.

        The task stops by itself once all tracked child runs finish, and calling this again restarts it. It does
        nothing if the watcher is disabled or already running.
        """
        if self._watch_interval is None or self._client is None:
            return
        if self._watch_task is not None and not self._watch_task.done():
            return
        self._watch_task = asyncio.create_task(self._watch(self._watch_interval), name='budget-pool-watcher')

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
            if not self._has_unfinished_child_runs():
                return

    def _has_unfinished_child_runs(self) -> bool:
        return any(
            entry.is_child_run and entry.run_id is not None and not entry.is_finished
            for entry in self._state.entries.values()
        )

    def _remaining_usd(self) -> Decimal:
        committed = sum((entry.committed_usd for entry in self._state.entries.values()), start=Decimal(0))
        return max(Decimal(0), self.limit_usd - committed)

    def _find_run_entry(self, run_id: str) -> BudgetPoolEntry | None:
        entry = self._state.entries.get(run_id)
        if entry is not None:
            return entry
        return next((entry for entry in self._state.entries.values() if entry.run_id == run_id), None)

    async def _refresh_runs(self) -> bool:
        """Update unfinished child runs from the API. Returns whether anything changed."""
        if self._client is None:
            return False

        entries = [
            entry
            for entry in self._state.entries.values()
            if entry.is_child_run and entry.run_id is not None and not entry.is_finished
        ]
        if not entries:
            return False

        runs = await asyncio.gather(
            *(self._client.run(entry.run_id).get() for entry in entries if entry.run_id is not None),
            return_exceptions=True,
        )

        changed = False
        for entry, run in zip(entries, runs, strict=True):
            if isinstance(run, BaseException):
                logger.warning(f'Failed to refresh the charges of run {entry.run_id}: {run}')
                continue
            if run is None:
                continue
            before = (entry.charged_usd, entry.is_finished)
            self._apply_run(entry, run)
            changed = changed or before != (entry.charged_usd, entry.is_finished)
        return changed

    @staticmethod
    def _apply_run(entry: BudgetPoolEntry, run: Run) -> None:
        entry.charged_usd = max(entry.charged_usd, get_run_charged_usd(run))
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
    the event prices are not known, the run's `usage_total_usd` is used instead.
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
