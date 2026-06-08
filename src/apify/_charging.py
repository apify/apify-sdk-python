from __future__ import annotations

import math
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Annotated, Literal, Protocol, TypedDict

from pydantic import BaseModel, ConfigDict, Field

import apify_client._models as _client_models
from apify_client._models import ActorChargeEvent as ClientActorChargeEvent
from apify_client._models import FlatPricePerMonthActorPricingInfo as ClientFlatPricePerMonth
from apify_client._models import FreeActorPricingInfo as ClientFree
from apify_client._models import PayPerEventActorPricingInfo as ClientPayPerEvent
from apify_client._models import PricePerDatasetItemActorPricingInfo as ClientPricePerDatasetItem
from apify_client._models import PricingPerEvent as ClientPricingPerEvent

from apify._utils import ReentrantLock, docs_group, ensure_context
from apify.log import logger
from apify.storages import Dataset

if TYPE_CHECKING:
    from types import TracebackType

    from apify_client import ApifyClientAsync

    from apify._configuration import Configuration

PricingModel = Literal['PAY_PER_EVENT', 'PRICE_PER_DATASET_ITEM', 'FLAT_PRICE_PER_MONTH', 'FREE']
"""Pricing model for an Actor."""

DEFAULT_DATASET_ITEM_EVENT = 'apify-default-dataset-item'

# Context variable to hold the current `ChargingManager` instance, if any. This allows PPE-aware dataset clients to
# access the charging manager without needing to pass it explicitly.
charging_manager_ctx: ContextVar[ChargingManager | None] = ContextVar('charging_manager_ctx', default=None)

_ensure_context = ensure_context('active')


# SDK-side Actor pricing-info models.
#
# These are thin subclasses of the `apify-client` pricing models. The Apify platform serializes Actor
# pricing info into the `APIFY_ACTOR_PRICING_INFO` env var (parsed by `Configuration.actor_pricing_info`),
# but omits several fields that `apify-client` v3 marks as required (`apifyMarginPercentage`, `createdAt`,
# `startedAt`, per-event `eventDescription`, and per-variant `trialMinutes` / `pricePerUnitUsd` / `unitName`).
# Each subclass relaxes only those omitted fields to optional, so the env var deserializes without faking
# values. Because every subclass is-a `apify-client` model, the API-returned `Run.pricing_info` (already an
# `apify-client` instance) flows through the same code paths without conversion.


class _RelaxedPricingMetadata(BaseModel):
    """Mixin relaxing the `CommonActorPricingInfo` metadata fields the platform env var omits."""

    model_config = ConfigDict(populate_by_name=True, extra='allow')

    apify_margin_percentage: Annotated[float | None, Field(alias='apifyMarginPercentage')] = None
    created_at: Annotated[datetime | None, Field(alias='createdAt')] = None
    started_at: Annotated[datetime | None, Field(alias='startedAt')] = None


@docs_group('Charging')
class ActorChargeEvent(ClientActorChargeEvent):
    # `event_description` is required in apify-client but omitted from the env var.
    event_description: Annotated[str | None, Field(alias='eventDescription')] = None


@docs_group('Charging')
class PricingPerEvent(ClientPricingPerEvent):
    actor_charge_events: Annotated[dict[str, ActorChargeEvent] | None, Field(alias='actorChargeEvents')] = None


@docs_group('Charging')
class FreeActorPricingInfo(_RelaxedPricingMetadata, ClientFree):
    pass


@docs_group('Charging')
class FlatPricePerMonthActorPricingInfo(_RelaxedPricingMetadata, ClientFlatPricePerMonth):
    trial_minutes: Annotated[int | None, Field(alias='trialMinutes')] = None
    price_per_unit_usd: Annotated[float | None, Field(alias='pricePerUnitUsd')] = None


@docs_group('Charging')
class PricePerDatasetItemActorPricingInfo(_RelaxedPricingMetadata, ClientPricePerDatasetItem):
    unit_name: Annotated[str | None, Field(alias='unitName')] = None
    # `price_per_unit_usd` is already optional in apify-client - inherited.


@docs_group('Charging')
class PayPerEventActorPricingInfo(_RelaxedPricingMetadata, ClientPayPerEvent):
    # Re-typed to the relaxed element so an omitted `eventDescription` validates; the field stays required.
    pricing_per_event: Annotated[PricingPerEvent, Field(alias='pricingPerEvent')]


ActorPricingInfoModel = ClientFree | ClientFlatPricePerMonth | ClientPricePerDatasetItem | ClientPayPerEvent
"""Common supertype of both env-var-parsed SDK subclasses and the API-returned `Run.pricing_info`."""

# apify-client ships these models with deferred forward refs (`__pydantic_complete__` is False), so the
# subclasses must be rebuilt - with the `TieredPricing*` names in scope - before the env-var discriminated
# union can validate standalone.
_pricing_rebuild_namespace = vars(_client_models) | {
    'ActorChargeEvent': ActorChargeEvent,
    'PricingPerEvent': PricingPerEvent,
}
for _pricing_model in (
    ActorChargeEvent,
    PricingPerEvent,
    FreeActorPricingInfo,
    FlatPricePerMonthActorPricingInfo,
    PricePerDatasetItemActorPricingInfo,
    PayPerEventActorPricingInfo,
):
    _pricing_model.model_rebuild(_types_namespace=_pricing_rebuild_namespace)


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

    async def charge(self, event_name: str, *, count: int = 1) -> ChargeResult:
        """Charge for a specified number of events - sub-operations of the Actor.

        This is relevant only for the pay-per-event pricing model.

        Args:
            event_name: Name of the event to be charged for.
            count: Number of events to charge for.
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

        Args:
            items_count: The number of items to be pushed.
            event_name: The explicit event name to charge for each item.
            is_default_dataset: Whether the data is pushed to the default dataset.
                If True, the synthetic event cost is included in the combined price.

        Returns:
            Max number of items that can be pushed within the budget.
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

        # Load per-event pricing information. Check against the apify-client base so both env-var-parsed
        # SDK subclasses and the API-returned model match.
        if isinstance(pricing_info, ClientPayPerEvent):
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
    async def charge(self, event_name: str, *, count: int = 1) -> ChargeResult:
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
            # Determine the maximum amount of events that can be charged within the budget
            max_chargeable = self.calculate_max_event_charge_count_within_limit(event_name)
            charged_count = min(count, max_chargeable if max_chargeable is not None else count)

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

            # Update the charging state
            self._charging_state.setdefault(event_name, ChargingStateItem(0, Decimal()))
            self._charging_state[event_name].charge_count += charged_count
            self._charging_state[event_name].total_charged_amount += charged_count * pricing_info.price

            # If running on the platform, call the charge endpoint
            if self._is_at_home:
                if self._actor_run_id is None:
                    raise RuntimeError('Actor run ID not configured')

                if event_name.startswith('apify-'):
                    # Synthetic events (e.g. apify-default-dataset-item) are tracked internally only,
                    # the platform handles them automatically based on dataset writes.
                    pass
                elif event_name in self._pricing_info:
                    await self._client.run(self._actor_run_id).charge(event_name, count=charged_count)
                elif event_name in self._tier_priced_events:
                    logger.warning(
                        f"Event '{event_name}' is tier-priced and is not chargeable via the pay-per-event API."
                    )
                else:
                    logger.warning(f"Attempting to charge for an unknown event '{event_name}'")

            # Log the charged operation (if enabled)
            if self._charging_log_dataset:
                await self._charging_log_dataset.push_data(
                    {
                        'event_name': event_name,
                        'event_title': pricing_info.title,
                        'event_price_usd': float(round(pricing_info.price, 3)),
                        'charged_count': charged_count,
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
        explicit_price = self._get_event_price(event_name)
        synthetic_price = self._get_event_price(DEFAULT_DATASET_ITEM_EVENT) if is_default_dataset else Decimal(0)
        combined_price = explicit_price + synthetic_price

        if not combined_price:
            return items_count

        result = (self._max_total_charge_usd - self.calculate_total_charged_amount()) / combined_price
        max_count = max(0, math.floor(result)) if result.is_finite() else items_count
        return min(items_count, max_count)

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
            return _FetchedPricingInfoDict(
                pricing_info=self._configuration.actor_pricing_info,
                charged_event_counts=self._configuration.charged_event_counts,
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


class _FetchedPricingInfoDict(TypedDict):
    pricing_info: ActorPricingInfoModel | None
    charged_event_counts: dict[str, int]
    max_total_charge_usd: Decimal
