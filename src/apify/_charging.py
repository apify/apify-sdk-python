from __future__ import annotations

import logging
import math
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from logging import getLogger
from typing import TYPE_CHECKING, Literal, Protocol, TypedDict

from cachetools import TTLCache

from apify_client._models import (
    FlatPricePerMonthActorPricingInfo,
    FreeActorPricingInfo,
    PayPerEventActorPricingInfo,
    PricePerDatasetItemActorPricingInfo,
)

from apify._utils import ReentrantLock, docs_group, ensure_context
from apify.storages import Dataset

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from types import TracebackType

    from apify_client import ApifyClientAsync

    from apify._configuration import Configuration

logger = getLogger(__name__)

charging_manager_ctx: ContextVar[ChargingManager | None] = ContextVar('charging_manager_ctx', default=None)
"""Holds the current `ChargingManager` instance, if any.

Allows PPE-aware dataset clients to access the charging manager without needing to pass it explicitly.
"""

DEFAULT_DATASET_ITEM_EVENT = 'apify-default-dataset-item'
"""Name of the synthetic event charged for each item pushed to the default dataset."""

ACTOR_START_EVENT = 'apify-actor-start'
"""Name of the synthetic event the platform charges when the run starts. The SDK never charges it."""

PricingModel = Literal['PAY_PER_EVENT', 'PRICE_PER_DATASET_ITEM', 'FLAT_PRICE_PER_MONTH', 'FREE']
"""Pricing model for an Actor."""

_ensure_context = ensure_context('active')


@asynccontextmanager
async def charge_lock_if_charging() -> AsyncGenerator[None]:
    """Acquire the charge lock if a charging manager is active, otherwise proceed without locking.

    The lock keeps a limit reservation and the charge that follows it atomic. Only pay-per-event runs charge
    anything, and `charging_manager_ctx` is set exactly for those, so for any other run there is nothing to
    serialize and the lock is skipped.
    """
    charging_manager = charging_manager_ctx.get()
    if charging_manager is None:
        yield
        return

    async with charging_manager.charge_lock():
        yield


ActorPricingInfoModel = (
    FreeActorPricingInfo
    | FlatPricePerMonthActorPricingInfo
    | PricePerDatasetItemActorPricingInfo
    | PayPerEventActorPricingInfo
)
"""Pricing info of an Actor run, parsed from the env var or returned by the API."""


@docs_group('Charging')
class ChargingManager(Protocol):
    """Provides fine-grained access to pay-per-event functionality.

    The ChargingManager allows you to charge for specific events in your Actor when using
    the pay-per-event pricing model. This enables precise cost control and transparent
    billing for different operations within your Actor.

    ### References

    - Apify platform documentation: https://docs.apify.com/platform/actors/publishing/monetize
    """

    charge_lock: ReentrantLock
    """Lock to synchronize charge operations. Prevents race conditions between `charge` and `push_data` calls."""

    async def charge(self, event_name: str, *, count: int = 1, idempotency_key: str | None = None) -> ChargeResult:
        """Charge for a specified number of events - sub-operations of the Actor.

        This is relevant only for the pay-per-event pricing model.

        When `count` exceeds the remaining budget, the events that fit are charged plus one more, so that the platform
        detects the exhausted budget and terminates the run. A run already strictly over budget charges nothing.

        Args:
            event_name: Name of the event to be charged for.
            count: Number of events to charge for.
            idempotency_key: A unique key preventing a retried operation from being charged for twice. A repeat
                under the same key within three minutes is not sent to the API and reports the `charged_count` of
                the original call, or zero if it names a different event. Like the platform, the key is forgotten
                afterwards.
        """

    def calculate_total_charged_amount(self) -> Decimal:
        """Calculate the total amount of money charged for pay-per-event events so far."""

    def calculate_max_event_charge_count_within_limit(self, event_name: str) -> int | None:
        """Calculate how many instances of an event can be charged before we reach the configured limit.

        Args:
            event_name: Name of the inspected event.
        """

    def get_pricing_info(self) -> ActorPricingInfo:
        """Retrieve detailed information about the effective pricing of the current Actor run.

        This can be used for instance when your code needs to support multiple pricing models in transition periods.
        """

    def get_charged_event_count(self, event_name: str) -> int:
        """Get the number of events with the given name that were charged so far.

        Args:
            event_name: Name of the inspected event.
        """

    def get_max_total_charge_usd(self) -> Decimal:
        """Get the configured maximum total charge for this Actor run."""

    def compute_push_data_limit(
        self,
        items_count: int,
        event_name: str,
        *,
        is_default_dataset: bool,
    ) -> int:
        """Compute how many items can be pushed and charged within the current budget.

        Accounts for both the explicit event and the synthetic `DEFAULT_DATASET_ITEM_EVENT` event,
        so that the combined cost per item does not exceed the remaining budget.

        When the budget cannot cover a single item, one item is still allowed through, so that the resulting overcharge
        makes the platform terminate the run. A run that is already strictly over budget gets no items through.

        Args:
            items_count: The number of items to be pushed.
            event_name: The explicit event name to charge for each item.
            is_default_dataset: Whether the data is pushed to the default dataset.
                If True, the synthetic event cost is included in the combined price.

        Returns:
            Max number of items to push.
        """

    def is_event_charge_limit_reached(self, event_name: str) -> bool:
        """Return True if the remaining budget is insufficient to charge even a single event of the given type."""

    def compute_chargeable(self) -> dict[str, int | None]:
        """Compute the maximum number of events of each type that can be charged within the current budget."""


@docs_group('Charging')
@dataclass(frozen=True)
class ChargeResult:
    """Result of the `ChargingManager.charge` method."""

    event_charge_limit_reached: bool
    """If true, no more events of this type can be charged within the limit."""

    charged_count: int
    """Total amount of charged events - may be lower than the requested amount."""

    chargeable_within_limit: dict[str, int | None]
    """How many events of each known type can still be charged within the limit."""


@docs_group('Charging')
@dataclass
class ActorPricingInfo:
    """Result of the `ChargingManager.get_pricing_info` method."""

    pricing_model: PricingModel | None
    """The currently effective pricing model."""

    max_total_charge_usd: Decimal
    """A configured limit for the total charged amount - if you exceed it, you won't receive more money than this."""

    is_pay_per_event: bool
    """A shortcut - true if the Actor runs with the pay-per-event pricing model."""

    per_event_prices: dict[str, Decimal]
    """Price of every known event type."""


class ChargingManagerImplementation(ChargingManager):
    """Implementation of the `ChargingManager` Protocol - this is only meant to be instantiated internally."""

    LOCAL_CHARGING_LOG_DATASET_NAME = 'charging-log'

    def __init__(self, configuration: Configuration, client: ApifyClientAsync) -> None:
        self._max_total_charge_usd = (
            configuration.max_total_charge_usd if configuration.max_total_charge_usd is not None else Decimal('inf')
        )
        self._configuration = configuration
        self._is_at_home = configuration.is_at_home
        self._actor_run_id = configuration.actor_run_id
        self._purge_charging_log_dataset = configuration.purge_on_start
        self._pricing_model: PricingModel | None = None

        self._client = client
        self._charging_log_dataset: Dataset | None = None

        self._charging_state: dict[str, ChargingStateItem] = {}
        self._pricing_info: dict[str, PricingInfoItem] = {}
        self._tier_priced_events: set[str] = set()
        self._idempotent_charges: TTLCache[str, IdempotentChargeItem] = TTLCache(maxsize=float('inf'), ttl=180)
        """Charges made with an idempotency key, by key. Keys expire after three minutes, the same as the platform's
        own idempotency records."""

        self._not_ppe_warning_printed = False
        self.active = False

        self.charge_lock = ReentrantLock()

    async def __aenter__(self) -> None:
        """Initialize the charging manager - this is called by the `Actor` class and shouldn't be invoked manually."""
        # Validate config
        if self._configuration.test_pay_per_event and self._is_at_home:
            raise ValueError(
                'Using the ACTOR_TEST_PAY_PER_EVENT environment variable is only supported '
                'in a local development environment'
            )

        self.active = True

        # Retrieve pricing information from env vars or API
        pricing_data = await self._fetch_pricing_info()
        pricing_info = pricing_data['pricing_info']
        charged_event_counts = pricing_data['charged_event_counts']
        max_total_charge_usd = pricing_data['max_total_charge_usd']

        # Set pricing model
        if self._configuration.test_pay_per_event:
            self._pricing_model: PricingModel = 'PAY_PER_EVENT'
        else:
            self._pricing_model = pricing_info.pricing_model if pricing_info else None

        # Load per-event pricing information
        if isinstance(pricing_info, PayPerEventActorPricingInfo):
            actor_charge_events = pricing_info.pricing_per_event.actor_charge_events or {}
            for event_name, event_pricing in actor_charge_events.items():
                if event_pricing.event_price_usd is None:
                    # Tier-priced event - not chargeable via the SDK's flat-price path; tracked so a later
                    # charge attempt is reported accurately rather than as an "unknown event".
                    self._tier_priced_events.add(event_name)
                    continue
                self._pricing_info[event_name] = PricingInfoItem(
                    price=Decimal(str(event_pricing.event_price_usd)),
                    title=event_pricing.event_title,
                )

            self._max_total_charge_usd = max_total_charge_usd

        # Load charged event counts
        for event_name, count in charged_event_counts.items():
            price = self._pricing_info.get(event_name, PricingInfoItem(Decimal(), title='')).price
            self._charging_state[event_name] = ChargingStateItem(
                charge_count=count,
                total_charged_amount=count * price,
            )

        # Set up charging log dataset for local development
        if not self._is_at_home and self._pricing_model == 'PAY_PER_EVENT':
            # We are not running on the Apify platform, but PPE is enabled for testing - open a dataset that
            # will contain a log of all charge calls for debugging purposes.

            if self._purge_charging_log_dataset:
                dataset = await Dataset.open(name=self.LOCAL_CHARGING_LOG_DATASET_NAME)
                await dataset.drop()

            self._charging_log_dataset = await Dataset.open(name=self.LOCAL_CHARGING_LOG_DATASET_NAME)

        # if the Actor runs with the pay-per-event pricing model, set the context variable so that PPE-aware dataset
        # clients can access the charging manager and charge for synthetic events.
        if self._pricing_model == 'PAY_PER_EVENT':
            charging_manager_ctx.set(self)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        if not self.active:
            raise RuntimeError('Exiting an uninitialized ChargingManager')

        charging_manager_ctx.set(None)
        self.active = False

    @_ensure_context
    async def charge(self, event_name: str, *, count: int = 1, idempotency_key: str | None = None) -> ChargeResult:
        if idempotency_key is not None and not idempotency_key.strip():
            raise ValueError('idempotency_key must not be blank')

        # For runs that do not use the pay-per-event pricing model, just print a warning and return
        if self._pricing_model != 'PAY_PER_EVENT':
            if not self._not_ppe_warning_printed:
                logger.warning(
                    'Ignored attempt to charge for an event - the Actor does not use the pay-per-event pricing'
                )
                self._not_ppe_warning_printed = True

            return ChargeResult(
                event_charge_limit_reached=False,
                charged_count=0,
                chargeable_within_limit=self.compute_chargeable(),
            )

        if count <= 0:
            return ChargeResult(
                event_charge_limit_reached=self.is_event_charge_limit_reached(event_name),
                charged_count=0,
                chargeable_within_limit=self.compute_chargeable(),
            )

        async with self.charge_lock():
            # A repeat the platform would discard is resolved here too - counting it would inflate the charging state
            # and make the run hit `max_total_charge_usd` early. The key alone decides, as on the platform.
            if idempotency_key is not None and (previous := self._idempotent_charges.get(idempotency_key)) is not None:
                if previous.event_name == event_name:
                    logger.debug(f"Skipped a repeated charge of event '{event_name}' under key '{idempotency_key}'.")
                    repeated_count = previous.charged_count
                else:
                    logger.warning(
                        f"Idempotency key '{idempotency_key}' was already used to charge for event "
                        f"'{previous.event_name}', so the charge of event '{event_name}' is skipped."
                    )
                    repeated_count = 0

                return ChargeResult(
                    event_charge_limit_reached=self.is_event_charge_limit_reached(event_name),
                    charged_count=repeated_count,
                    chargeable_within_limit=self.compute_chargeable(),
                )

            charged_count = self._compute_charged_count(event_name, count)

            if charged_count == 0:
                return ChargeResult(
                    event_charge_limit_reached=True,
                    charged_count=0,
                    chargeable_within_limit=self.compute_chargeable(),
                )

            pricing_info = self._pricing_info.get(
                event_name,
                PricingInfoItem(
                    # Use a nonzero price for local development so that the maximum budget can be reached.
                    price=Decimal() if self._is_at_home else Decimal(1),
                    title=f"Unknown event '{event_name}'",
                ),
            )

            # If running on the platform, call the charge endpoint
            if self._is_at_home:
                if self._actor_run_id is None:
                    raise RuntimeError('Actor run ID not configured')

                if event_name.startswith('apify-'):
                    # Synthetic events (e.g. apify-default-dataset-item) are tracked internally only,
                    # the platform handles them automatically based on dataset writes.
                    pass
                elif event_name in self._pricing_info:
                    await self._client.run(self._actor_run_id).charge(
                        event_name,
                        count=charged_count,
                        idempotency_key=idempotency_key,
                    )
                    logger.debug(f"Charged {charged_count} occurrence(s) of event '{event_name}'.")
                elif event_name in self._tier_priced_events:
                    logger.warning(
                        f"Event '{event_name}' is tier-priced and is not chargeable via the pay-per-event API."
                    )
                else:
                    logger.warning(f"Attempting to charge for an unknown event '{event_name}'")

            # Count the charge only after the API call succeeds, so a failed call retried under the same key is
            # counted once.
            self._charging_state.setdefault(event_name, ChargingStateItem(0, Decimal()))
            self._charging_state[event_name].charge_count += charged_count
            self._charging_state[event_name].total_charged_amount += charged_count * pricing_info.price

            # Remember the key for every charge that was counted, including events the API never receives, such as
            # synthetic and tier-priced ones - those are counted locally and a repeat would count them twice.
            if idempotency_key is not None:
                self._idempotent_charges[idempotency_key] = IdempotentChargeItem(
                    event_name=event_name,
                    charged_count=charged_count,
                )

            # Log the charged operation (if enabled)
            if self._charging_log_dataset:
                await self._charging_log_dataset.push_data(
                    {
                        'event_name': event_name,
                        'event_title': pricing_info.title,
                        'event_price_usd': float(round(pricing_info.price, 3)),
                        'charged_count': charged_count,
                        'idempotency_key': idempotency_key,
                        'timestamp': datetime.now(UTC).isoformat(),
                    }
                )

            # If it is not possible to charge the full amount, log that fact
            if charged_count < count:
                subject = 'instance' if count == 1 else 'instances'
                logger.info(
                    f"Charging {count} {subject} of '{event_name}' event would exceed max_total_charge_usd "
                    f'- only {charged_count} events were charged'
                )

            return ChargeResult(
                event_charge_limit_reached=self.is_event_charge_limit_reached(event_name),
                charged_count=charged_count,
                chargeable_within_limit=self.compute_chargeable(),
            )

    @_ensure_context
    def calculate_total_charged_amount(self) -> Decimal:
        return sum(
            (item.total_charged_amount for item in self._charging_state.values()),
            start=Decimal(),
        )

    @_ensure_context
    def calculate_max_event_charge_count_within_limit(self, event_name: str) -> int | None:
        price = self._get_event_price(event_name)

        if not price:
            return None

        result = (self._max_total_charge_usd - self.calculate_total_charged_amount()) / price
        return max(0, math.floor(result)) if result.is_finite() else None

    @_ensure_context
    def get_pricing_info(self) -> ActorPricingInfo:
        return ActorPricingInfo(
            pricing_model=self._pricing_model,
            is_pay_per_event=self._pricing_model == 'PAY_PER_EVENT',
            max_total_charge_usd=self._max_total_charge_usd
            if self._max_total_charge_usd is not None
            else Decimal('inf'),
            per_event_prices={
                event_name: pricing_info.price for event_name, pricing_info in self._pricing_info.items()
            },
        )

    @_ensure_context
    def get_charged_event_count(self, event_name: str) -> int:
        item = self._charging_state.get(event_name)
        return item.charge_count if item is not None else 0

    @_ensure_context
    def get_max_total_charge_usd(self) -> Decimal:
        return self._max_total_charge_usd

    @_ensure_context
    def compute_push_data_limit(
        self,
        items_count: int,
        event_name: str,
        *,
        is_default_dataset: bool,
    ) -> int:
        if self._pricing_model != 'PAY_PER_EVENT' or items_count == 0:
            return items_count

        explicit_price = self._get_event_price(event_name)
        synthetic_price = self._get_event_price(DEFAULT_DATASET_ITEM_EVENT) if is_default_dataset else Decimal(0)
        combined_price = explicit_price + synthetic_price

        if not combined_price:
            return items_count

        result = (self._max_total_charge_usd - self.calculate_total_charged_amount()) / combined_price
        max_count = max(0, math.floor(result)) if result.is_finite() else items_count

        if max_count >= items_count:
            return items_count

        if max_count > 0:
            return max_count

        return 1 if self.calculate_total_charged_amount() <= self._max_total_charge_usd else 0

    @_ensure_context
    def is_event_charge_limit_reached(self, event_name: str) -> bool:
        max_charge_count = self.calculate_max_event_charge_count_within_limit(event_name)
        return max_charge_count is not None and max_charge_count <= 0

    @_ensure_context
    def compute_chargeable(self) -> dict[str, int | None]:
        return {
            event_name: self.calculate_max_event_charge_count_within_limit(event_name)
            for event_name in self._pricing_info
        }

    async def _fetch_pricing_info(self) -> _FetchedPricingInfoDict:
        """Fetch pricing information from environment variables or API."""
        # Check if pricing info is available via environment variables
        if self._configuration.actor_pricing_info is not None and self._configuration.charged_event_counts is not None:
            charged_event_counts = self._configuration.charged_event_counts

            # The platform fills the env var with the counts recorded when the run started. A container started
            # after a reboot, migration or restart would miss what the run charged before it, and a restart cannot
            # be told apart from a first start, so every start takes the current counts from the run.
            if self._is_chargeable_platform_run(self._configuration.actor_pricing_info):
                charged_event_counts = await self._fetch_current_charged_event_counts(charged_event_counts)

            return _FetchedPricingInfoDict(
                pricing_info=self._configuration.actor_pricing_info,
                charged_event_counts=charged_event_counts,
                max_total_charge_usd=(
                    self._configuration.max_total_charge_usd
                    if self._configuration.max_total_charge_usd is not None
                    else Decimal('inf')
                ),
            )

        # Fall back to API call
        if self._is_at_home:
            if self._actor_run_id is None:
                raise RuntimeError('Actor run ID not found even though the Actor is running on Apify')

            run = await self._client.run(self._actor_run_id).get()

            if run is None:
                raise RuntimeError('Actor run not found')

            max_charge = run.options.max_total_charge_usd
            return _FetchedPricingInfoDict(
                pricing_info=run.pricing_info,
                charged_event_counts=run.charged_event_counts or {},
                max_total_charge_usd=Decimal(str(max_charge)) if max_charge is not None else Decimal('inf'),
            )

        # Local development without environment variables
        return _FetchedPricingInfoDict(
            pricing_info=None,
            charged_event_counts={},
            max_total_charge_usd=(
                self._configuration.max_total_charge_usd
                if self._configuration.max_total_charge_usd is not None
                else Decimal('inf')
            ),
        )

    def _is_chargeable_platform_run(self, pricing_info: ActorPricingInfoModel) -> bool:
        """Whether this is a platform run the SDK charges events for.

        A run is chargeable when its pricing has at least one priced event other than the start event, which only
        the platform charges. For any other run the charged event counts cannot have moved since the run started.
        """
        if not self._is_at_home or not isinstance(pricing_info, PayPerEventActorPricingInfo):
            return False

        actor_charge_events = pricing_info.pricing_per_event.actor_charge_events or {}
        return any(
            event_name != ACTOR_START_EVENT and event_pricing.event_price_usd is not None
            for event_name, event_pricing in actor_charge_events.items()
        )

    async def _fetch_current_charged_event_counts(self, initial_counts: dict[str, int]) -> dict[str, int]:
        """Merge the counts recorded when the run started with the run's current counts, taking the higher of each.

        The run is read through the API. When that fails, the initial counts are kept and a warning is logged, since
        a run that cannot refresh its counts is still better off running than failing to start.
        """
        if self._actor_run_id is None:
            raise RuntimeError('Actor run ID not found even though the Actor is running on Apify')

        try:
            run = await self._client.run(self._actor_run_id).get()
        except Exception:
            logger.warning(
                'Failed to fetch the current charged event counts of the run, continuing with the counts recorded '
                'when the run started.',
                exc_info=True,
            )
            return initial_counts

        if run is None:
            logger.warning(
                'Actor run not found when fetching the current charged event counts, continuing with the counts '
                'recorded when the run started.'
            )
            return initial_counts

        merged_counts = dict(initial_counts)
        for event_name, count in (run.charged_event_counts or {}).items():
            merged_counts[event_name] = max(merged_counts.get(event_name, 0), count)

        # Counts moved only when an earlier container of this run charged something, which is worth a note.
        log_level = logging.INFO if merged_counts != initial_counts else logging.DEBUG
        logger.log(
            log_level,
            'Loaded the current charged event counts from the run.',
            extra={
                'charged_event_counts': merged_counts,
                'reboot_count': run.stats.reboot_count,
                'migration_count': run.stats.migration_count,
                'restart_count': run.stats.restart_count,
                'resurrect_count': run.stats.resurrect_count,
            },
        )
        return merged_counts

    def _compute_charged_count(self, event_name: str, count: int) -> int:
        """Compute how many of `count` events to charge, given the remaining budget."""
        max_chargeable = self.calculate_max_event_charge_count_within_limit(event_name)
        if max_chargeable is None or count <= max_chargeable:
            return count

        # Overcharge by one event, so that the platform detects the exhausted budget and terminates the run. A run
        # already strictly over budget gets no further charges.
        if self.calculate_total_charged_amount() <= self._max_total_charge_usd:
            return max_chargeable + 1

        return 0

    def _get_event_price(self, event_name: str) -> Decimal:
        pricing_info = self._pricing_info.get(event_name)
        if pricing_info is not None:
            return pricing_info.price
        return Decimal(0) if self._is_at_home else Decimal(1)


@dataclass
class ChargingStateItem:
    charge_count: int
    total_charged_amount: Decimal


@dataclass
class PricingInfoItem:
    price: Decimal
    title: str


@dataclass(frozen=True)
class IdempotentChargeItem:
    event_name: str
    charged_count: int


class _FetchedPricingInfoDict(TypedDict):
    pricing_info: ActorPricingInfoModel | None
    charged_event_counts: dict[str, int]
    max_total_charge_usd: Decimal
