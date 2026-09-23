from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from logging import getLogger
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic.alias_generators import to_camel

from apify_client._models import PayPerEventActorPricingInfo as ClientPayPerEvent
from crawlee._utils.crypto import crypto_random_object_id

from apify._utils import docs_group

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from apify_client import ApifyClientAsync
    from apify_client._models import Run

    from apify.storages import Dataset

logger = getLogger(__name__)

DEFAULT_BUDGET_POOL_ALIAS = 'apify-budget-pool'
"""Alias of the dataset holding the default budget pool of an Actor run."""

BUDGET_POOL_POLL_INTERVAL = timedelta(seconds=5)
"""How often a budget pool polls its running child runs for their charges by default."""

BudgetPoolRunStatus = Literal['RUNNING', 'FINISHED', 'ABORTED_BY_POOL']
"""Status of a run as recorded in a budget pool."""

_TERMINAL_RUN_STATUSES = frozenset({'SUCCEEDED', 'FAILED', 'TIMED-OUT', 'ABORTED'})


@docs_group('Charging')
class BudgetExhaustedError(RuntimeError):
    """Raised when a budget pool has no budget left for another child run."""


@docs_group('Charging')
@dataclass(frozen=True)
class BudgetPoolEvent:
    """A single observation of a run's charges, appended to a budget pool."""

    at: datetime
    """When the charges were observed."""

    charged_usd: Decimal
    """The total amount the run had charged at that time."""

    status: BudgetPoolRunStatus
    """The status of the run at that time."""


@docs_group('Charging')
@dataclass
class BudgetPoolEntry:
    """A run charging against a budget pool, with the history of its charges."""

    run_id: str
    """ID of the run."""

    events: list[BudgetPoolEvent] = field(default_factory=list)
    """Observations of the run's charges, oldest first. Each one charged more than the previous ones, or finished
    the run."""

    actor_id: str | None = None
    """ID of the Actor of the run, if it was started through a budget pool."""

    max_charge_usd: Decimal | None = None
    """The `max_total_charge_usd` the run was started with, if it was started through a budget pool."""

    parent_run_id: str | None = None
    """ID of the run that started this run through a budget pool, if any."""

    @property
    def charged_usd(self) -> Decimal:
        """The highest amount the run was observed to have charged."""
        return max((event.charged_usd for event in self.events), default=Decimal(0))

    @property
    def status(self) -> BudgetPoolRunStatus:
        """The latest recorded status of the run."""
        statuses = {event.status for event in self.events}
        if 'ABORTED_BY_POOL' in statuses:
            return 'ABORTED_BY_POOL'
        if 'FINISHED' in statuses:
            return 'FINISHED'
        return 'RUNNING'

    @property
    def is_finished(self) -> bool:
        """Whether the run is recorded as finished."""
        return self.status != 'RUNNING'


@docs_group('Charging')
@dataclass(frozen=True)
class BudgetAllocation:
    """Result of `BudgetPool.allocate` - the budget a child run is about to be started with."""

    id: str
    """ID of the allocation, to pass to `BudgetPool.track_run` or `BudgetPool.release`."""

    amount_usd: Decimal
    """The allocated amount - pass it to the child run as `max_total_charge_usd`. Infinite for an unlimited pool."""


class _RunMetadata(BaseModel):
    """Written once, by the run that started the child, when the child starts."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    actor_id: str | None = None
    max_charge_usd: Decimal | None = None
    parent_run_id: str | None = None


@dataclass
class _Allocation:
    amount_usd: Decimal
    actor_id: str | None


@docs_group('Charging')
class BudgetPool:
    """A charge budget shared by several Actor runs, persisted in a dataset.

    The pool is an append-only log of charge observations, one list per run:

    ```
    {"run123": [(t1, 0.12), (t2, 0.135)], "run456": [(t3, 0.02), (t4, 0.135)]}
    ```

    An observation is appended only when it is higher than any seen so far for the run, so a run's charges are the
    maximum of its observations, and the pool's charges are the sum of those maximums over all runs.

    The log is kept in a dataset, which only ever appends items and never modifies them, so runs sharing a pool
    never overwrite each other's data, and no locking is needed: writers that race only add observations, and the
    maximum ignores stale ones. Items keep their order, so each reader fetches only the items appended since its
    previous read. Besides charge observations, the dataset holds one item per child run started through the pool
    (its Actor, `max_total_charge_usd` and parent run) and the pool's limit.

    While child runs started through the pool are running, the pool polls them for their charges (every
    `BUDGET_POOL_POLL_INTERVAL` by default) and appends what it sees. A child gets the budget remaining when it
    starts as its `max_total_charge_usd`, which the platform enforces for pay-per-event Actors. When the charges in
    the pool exceed the limit, each run sharing the pool aborts the running children it started. A child that
    charges more than its own `max_total_charge_usd` - possible for Actors using another pricing model, or for
    orchestrators that do not limit their own children - is aborted too.

    Charges are only known when polled, so this is not a hard limit: the pool can overshoot it by what the children
    spend between two polls, plus the delay with which the Apify API reports charges and the dataset lists new
    items.

    Keep the pool in an aliased dataset of the run to survive migrations and restarts, or in a named dataset to
    share it by unrelated Actor runs. Never use the run's default dataset, as items pushed there are charged for.

    Use `Actor.open_budget_pool` to open a pool. When the Actor run has `max_total_charge_usd` set and uses the
    pay-per-event pricing model, `Actor.start` and `Actor.call` use a default pool limited to that amount.
    """

    def __init__(
        self,
        dataset: Dataset,
        *,
        limit_usd: Decimal | None = None,
        default_child_budget_usd: Decimal | None = None,
        client: ApifyClientAsync | None = None,
        owner_run_id: str | None = None,
        poll_interval: timedelta | None = BUDGET_POOL_POLL_INTERVAL,
    ) -> None:
        """Create a new instance. Prefer `Actor.open_budget_pool`, which also loads the stored state.

        Args:
            dataset: The dataset holding the pool. It must not be used for anything else.
            limit_usd: The total budget of the pool. If `None`, the limit stored in the pool is used, and if there
                is none, the pool is unlimited and only tracks costs.
            default_child_budget_usd: The `max_total_charge_usd` of a child run started without one, capped at
                the remaining budget. If `None`, such a child gets the whole remaining budget.
            client: The Apify API client used to poll the child runs and to abort them.
            owner_run_id: ID of the run using the pool. Child runs it started are resumed from the pool after
                a restart.
            poll_interval: How often the background watcher started by `start_watching` polls the running child
                runs. `None` disables the watcher, and with it aborting the children.
        """
        self._dataset = dataset
        self._limit_usd = limit_usd
        self._default_child_budget_usd = default_child_budget_usd
        self._client = client
        self._owner_run_id = owner_run_id
        self._poll_interval = poll_interval

        self._offset = 0
        self._stored_limit_usd: Decimal | None = None
        self._entries: dict[str, BudgetPoolEntry] = {}
        self._metadata: dict[str, _RunMetadata] = {}
        self._own_children: set[str] = set()
        self._allocations: dict[str, _Allocation] = {}
        self._charge_sources: dict[str, Callable[[], Decimal]] = {}

        self._lock = asyncio.Lock()
        self._watch_task: asyncio.Task[None] | None = None

    @classmethod
    async def open(
        cls,
        dataset: Dataset,
        *,
        limit_usd: Decimal | None = None,
        default_child_budget_usd: Decimal | None = None,
        client: ApifyClientAsync | None = None,
        owner_run_id: str | None = None,
        poll_interval: timedelta | None = BUDGET_POOL_POLL_INTERVAL,
    ) -> BudgetPool:
        """Open a budget pool stored in the given dataset.

        Args:
            dataset: The dataset holding the pool. It must not be used for anything else.
            limit_usd: The total budget of the pool. If set and different from the stored limit, it is also
                appended to the pool for others to use.
            default_child_budget_usd: The `max_total_charge_usd` of a child run started without one, capped at
                the remaining budget.
            client: The Apify API client used to poll the child runs and to abort them.
            owner_run_id: ID of the run using the pool. Child runs it started are resumed from the pool.
            poll_interval: How often the background watcher polls the running child runs. `None` disables it.
        """
        pool = cls(
            dataset,
            limit_usd=limit_usd,
            default_child_budget_usd=default_child_budget_usd,
            client=client,
            owner_run_id=owner_run_id,
            poll_interval=poll_interval,
        )
        async with pool._lock:
            await pool._load()
            if pool._owner_run_id is not None:
                pool._own_children.update(
                    run_id
                    for run_id, metadata in pool._metadata.items()
                    if metadata.parent_run_id == pool._owner_run_id
                )
            if limit_usd is not None and limit_usd != pool._stored_limit_usd:
                await dataset.push_data(
                    {'type': 'limit', 'at': datetime.now(UTC).isoformat(), 'limitUsd': str(limit_usd)}
                )
                pool._stored_limit_usd = limit_usd
        return pool

    @property
    def limit_usd(self) -> Decimal:
        """The total budget of the pool, `Decimal('inf')` for an unlimited pool."""
        limit_usd = self._limit_usd if self._limit_usd is not None else self._stored_limit_usd
        return limit_usd if limit_usd is not None else Decimal('inf')

    @property
    def default_child_budget_usd(self) -> Decimal | None:
        """The `max_total_charge_usd` of a child run started without one."""
        return self._default_child_budget_usd

    async def get_entries(self, *, refresh: bool = False) -> dict[str, BudgetPoolEntry]:
        """Return the runs charging against the pool, keyed by run ID, with the history of their charges.

        Args:
            refresh: Whether to first poll the running child runs for their current charges.
        """
        async with self._lock:
            await self._update(poll=refresh)
            return {
                run_id: BudgetPoolEntry(
                    run_id=entry.run_id,
                    events=list(entry.events),
                    actor_id=entry.actor_id,
                    max_charge_usd=entry.max_charge_usd,
                    parent_run_id=entry.parent_run_id,
                )
                for run_id, entry in self._entries.items()
            }

    async def get_charged_usd(self, *, refresh: bool = False) -> Decimal:
        """Return the total amount charged against the pool so far.

        Args:
            refresh: Whether to first poll the running child runs for their current charges.
        """
        async with self._lock:
            await self._update(poll=refresh)
            return self._charged_usd()

    async def get_remaining_usd(self, *, refresh: bool = True) -> Decimal:
        """Return the part of the limit not charged yet.

        Args:
            refresh: Whether to first poll the running child runs for their current charges.
        """
        async with self._lock:
            await self._update(poll=refresh)
            return self._remaining_usd()

    async def refresh(self) -> None:
        """Poll the running child runs for their current charges and append them to the pool."""
        async with self._lock:
            await self._update(poll=True)

    async def allocate(self, amount_usd: Decimal | None = None, *, actor_id: str | None = None) -> BudgetAllocation:
        """Decide the `max_total_charge_usd` of a child run about to be started.

        The pool is refreshed first, so the remaining budget is current. Nothing is appended to the pool until the
        run is started and passed to `track_run`.

        Args:
            amount_usd: The requested amount. It is capped at the remaining budget. If `None`, the pool's
                `default_child_budget_usd` is requested, or the whole remaining budget if that is not set either.
            actor_id: ID of the Actor the child run belongs to, stored for reference.

        Returns:
            The allocation. Its `amount_usd` is infinite if both the pool and the request are unlimited.

        Raises:
            BudgetExhaustedError: If there is no budget left.
        """
        if amount_usd is not None and amount_usd < 0:
            raise ValueError(f'The allocated amount must not be negative, got {amount_usd}.')

        async with self._lock:
            await self._update(poll=True)

            remaining = self._remaining_usd()
            requested = amount_usd if amount_usd is not None else self._default_child_budget_usd

            if remaining <= 0 and (requested is None or requested > 0):
                raise BudgetExhaustedError(
                    f'The budget pool has no budget left (limit {self.limit_usd} USD, '
                    f'charged {self._charged_usd()} USD).'
                )

            granted = remaining if requested is None else min(requested, remaining)
            if requested is not None and granted < requested:
                logger.info(f'Requested budget of {requested} USD capped at the remaining {granted} USD.')

            allocation_id = crypto_random_object_id()
            self._allocations[allocation_id] = _Allocation(amount_usd=granted, actor_id=actor_id)

        return BudgetAllocation(id=allocation_id, amount_usd=granted)

    async def release(self, allocation_id: str) -> None:
        """Drop an allocation whose child run was not started, e.g. because starting it failed.

        Args:
            allocation_id: ID of the allocation, as returned by `allocate`.
        """
        self._allocations.pop(allocation_id, None)

    async def track_run(self, allocation_id: str, run: Run) -> None:
        """Start tracking the child run started for an allocation, and append its current charges.

        Args:
            allocation_id: ID of the allocation, as returned by `allocate`.
            run: The child run started with the allocated budget.
        """
        allocation = self._allocations.pop(allocation_id, None)
        max_charge_usd = allocation.amount_usd if allocation is not None else None
        metadata = _RunMetadata(
            actor_id=run.act_id,
            max_charge_usd=max_charge_usd if max_charge_usd is not None and max_charge_usd.is_finite() else None,
            parent_run_id=self._owner_run_id,
        )

        async with self._lock:
            await self._dataset.push_data(
                {'type': 'run', 'runId': run.id, **metadata.model_dump(mode='json', by_alias=True)}
            )
            self._metadata[run.id] = metadata
            self._own_children.add(run.id)
            self._apply_metadata(self._get_entry(run.id), metadata)
            await self._append_run(run)

    async def update_run(self, run: Run) -> None:
        """Append the current charges and status of a run, e.g. after it finished.

        Args:
            run: The latest state of the run.
        """
        async with self._lock:
            await self._append_run(run)

    async def record_charges(self, run_id: str, charged_usd: Decimal) -> None:
        """Append the amount a run has charged by itself so far, e.g. the orchestrating run's own charges.

        Nothing is appended unless the amount is higher than any recorded so far. A run tracked in the pool both as
        a child and by its own charges is counted once, as its observations are grouped by run ID.

        Args:
            run_id: ID of the run.
            charged_usd: The total amount the run has charged so far.
        """
        async with self._lock:
            await self._append(run_id, charged_usd, 'RUNNING')

    def track_charges(self, run_id: str, get_charged_usd: Callable[[], Decimal]) -> None:
        """Keep appending a run's own charges on every refresh, e.g. the charges of the orchestrating run itself.

        Args:
            run_id: ID of the run.
            get_charged_usd: Returns the total amount the run has charged so far.
        """
        self._charge_sources[run_id] = get_charged_usd

    async def enforce(self) -> list[str]:
        """Refresh the pool and abort running child runs started by this pool if the budget is exceeded.

        All running children started through this pool instance are aborted when the charges in the pool exceed
        the limit. A single child is aborted when it charged more than its own `max_total_charge_usd`. Children
        started by other runs sharing the pool are left to those runs.

        Returns:
            IDs of the runs that were aborted.
        """
        async with self._lock:
            await self._update(poll=True)

            running = [run_id for run_id in self._own_children if not self._get_entry(run_id).is_finished]

            charged = self._charged_usd()
            is_pool_exceeded = charged > self.limit_usd
            if is_pool_exceeded and running:
                logger.warning(
                    f'The budget pool charges ({charged} USD) exceed its limit ({self.limit_usd} USD), '
                    f'aborting {len(running)} running child run(s).'
                )

            to_abort = [run_id for run_id in running if is_pool_exceeded or self._is_over_own_limit(run_id)]

            aborted: list[str] = []
            if self._client is None:
                return aborted

            for run_id in to_abort:
                if not is_pool_exceeded:
                    entry = self._get_entry(run_id)
                    logger.warning(
                        f'Aborting run {run_id}: it charged {entry.charged_usd} USD, beyond its '
                        f'max_total_charge_usd of {entry.max_charge_usd} USD.'
                    )
                try:
                    run = await self._client.run(run_id).abort()
                except Exception as exc:
                    logger.warning(f'Failed to abort run {run_id}: {exc}')
                    continue
                await self._append(run_id, get_run_charged_usd(run), 'ABORTED_BY_POOL')
                aborted.append(run_id)

            return aborted

    def start_watching(self) -> None:
        """Start a background task that calls `enforce` every poll interval while child runs are running.

        The task stops by itself once all child runs started through this pool instance finish, and calling this
        again restarts it. It does nothing if the watcher is disabled or already running.
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
            if not self._has_running_children():
                return

    def _has_running_children(self) -> bool:
        return any(not self._get_entry(run_id).is_finished for run_id in self._own_children)

    def _is_over_own_limit(self, run_id: str) -> bool:
        entry = self._get_entry(run_id)
        return entry.max_charge_usd is not None and entry.charged_usd > entry.max_charge_usd

    def _charged_usd(self) -> Decimal:
        return sum((entry.charged_usd for entry in self._entries.values()), start=Decimal(0))

    def _remaining_usd(self) -> Decimal:
        return max(Decimal(0), self.limit_usd - self._charged_usd())

    def _get_entry(self, run_id: str) -> BudgetPoolEntry:
        entry = self._entries.get(run_id)
        if entry is None:
            entry = self._entries[run_id] = BudgetPoolEntry(run_id=run_id)
        return entry

    @staticmethod
    def _apply_metadata(entry: BudgetPoolEntry, metadata: _RunMetadata) -> None:
        entry.actor_id = metadata.actor_id
        entry.max_charge_usd = metadata.max_charge_usd
        entry.parent_run_id = metadata.parent_run_id

    def _add_event(self, run_id: str, event: BudgetPoolEvent) -> None:
        entry = self._get_entry(run_id)
        if event not in entry.events:
            entry.events.append(event)
            entry.events.sort(key=lambda item: (item.at, item.charged_usd))

    async def _load(self) -> None:
        """Read the items appended to the pool since the previous read."""
        count = 0
        async for item in self._dataset.iterate_items(offset=self._offset):
            count += 1
            try:
                self._apply_item(item)
            except (KeyError, TypeError, ValueError, InvalidOperation, ValidationError) as exc:
                logger.warning(f'Ignoring an invalid budget pool item {item!r}: {exc}')
        self._offset += count

    def _apply_item(self, item: Mapping[str, Any]) -> None:
        item_type = item.get('type')
        if item_type == 'charge':
            status = item['status']
            if status not in {'RUNNING', 'FINISHED', 'ABORTED_BY_POOL'}:
                raise ValueError(f'unknown status {status!r}')
            event = BudgetPoolEvent(
                at=datetime.fromisoformat(item['at']),
                charged_usd=Decimal(str(item['chargedUsd'])),
                status=status,
            )
            self._add_event(str(item['runId']), event)
        elif item_type == 'run':
            run_id = str(item['runId'])
            metadata = _RunMetadata.model_validate(item)
            self._metadata[run_id] = metadata
            self._apply_metadata(self._get_entry(run_id), metadata)
        elif item_type == 'limit':
            self._stored_limit_usd = Decimal(str(item['limitUsd']))

    async def _update(self, *, poll: bool) -> None:
        await self._load()
        if not poll:
            return

        for run_id, get_charged_usd in self._charge_sources.items():
            await self._append(run_id, get_charged_usd(), 'RUNNING')

        if self._client is None:
            return

        running = [run_id for run_id in self._own_children if not self._get_entry(run_id).is_finished]
        runs = await asyncio.gather(
            *(self._client.run(run_id).get() for run_id in running),
            return_exceptions=True,
        )
        for run_id, run in zip(running, runs, strict=True):
            if isinstance(run, BaseException):
                logger.warning(f'Failed to poll the charges of run {run_id}: {run}')
            elif run is not None:
                await self._append_run(run)

    async def _append_run(self, run: Run) -> None:
        status: BudgetPoolRunStatus = 'FINISHED' if run.status in _TERMINAL_RUN_STATUSES else 'RUNNING'
        await self._append(run.id, get_run_charged_usd(run), status)

    async def _append(self, run_id: str, charged_usd: Decimal, status: BudgetPoolRunStatus) -> None:
        """Append an observation, unless it is neither the highest amount so far nor a new final status."""
        entry = self._get_entry(run_id)
        is_higher = not entry.events or charged_usd > entry.charged_usd
        is_new_status = status not in ('RUNNING', entry.status)
        if not is_higher and not is_new_status:
            return

        event = BudgetPoolEvent(at=datetime.now(UTC), charged_usd=max(charged_usd, entry.charged_usd), status=status)
        await self._dataset.push_data(
            {
                'type': 'charge',
                'runId': run_id,
                'at': event.at.isoformat(),
                'chargedUsd': str(event.charged_usd),
                'status': status,
            }
        )
        # The item is read back on a later load, and deduplicated against this copy.
        self._add_event(run_id, event)


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
