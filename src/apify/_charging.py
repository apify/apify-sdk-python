from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol, Union

from pydantic import TypeAdapter

from apify_shared.utils import ignore_docs
from crawlee._utils.context import ensure_context

from apify._models import ActorRun, PricingModel
from apify._utils import docs_group
from apify.log import logger
from apify.storages import Dataset

if TYPE_CHECKING:
    from types import TracebackType

    from apify_client import ApifyClientAsync

    from apify._configuration import Configuration


run_validator: TypeAdapter[ActorRun | None] = TypeAdapter(Union[ActorRun, None])


@docs_group('Interfaces')
class ChargingManager(Protocol):
    """Provides fine-grained access to pay-per-event functionality."""

    async def charge(self, event_name: str, count: int = 1) -> ChargeResult:
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


@docs_group('Data structures')
@dataclass(frozen=True)
class ChargeResult:
    """Result of the `ChargingManager.charge` method."""

    event_charge_limit_reached: bool
    """If true, no more events of this type can be charged within the limit."""

    charged_count: int
    """Total amount of charged events - may be lower than the requested amount."""

    chargeable_within_limit: dict[str, int | None]
    """How many events of each known type can still be charged within the limit."""


@docs_group('Data structures')
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


@ignore_docs
class ChargingManagerImplementation(ChargingManager):
    """Implementation of the `ChargingManager` Protocol - this is only meant to be instantiated internally."""

    LOCAL_CHARGING_LOG_DATASET_NAME = 'charging_log'

    def __init__(self, configuration: Configuration, client: ApifyClientAsync) -> None:
        self._max_total_charge_usd = configuration.max_total_charge_usd or Decimal('inf')
        self._is_at_home = configuration.is_at_home
        self._actor_run_id = configuration.actor_run_id
        self._purge_charging_log_dataset = configuration.purge_on_start
        self._pricing_model: PricingModel | None = None

        if configuration.test_pay_per_event:
            if self._is_at_home:
                raise ValueError(
                    'Using the ACTOR_TEST_PAY_PER_EVENT environment variable is only supported '
                    'in a local development environment'
                )

            self._pricing_model = 'PAY_PER_EVENT'

        self._client = client
        self._charging_log_dataset: Dataset | None = None

        self._charging_state: dict[str, ChargingStateItem] = {}
        self._pricing_info: dict[str, PricingInfoItem] = {}

        self._not_ppe_warning_printed = False
        self.active = False

    async def __aenter__(self) -> None:
        """Initialize the charging manager - this is called by the `Actor` class and shouldn't be invoked manually."""
        self.active = True

        if self._is_at_home:
            # Running on the Apify platform - fetch pricing info for the current run.

            if self._actor_run_id is None:
                raise RuntimeError('Actor run ID not found even though the Actor is running on Apify')

            run = run_validator.validate_python(await self._client.run(self._actor_run_id).get())
            if run is None:
                raise RuntimeError('Actor run not found')

            if run.pricing_info is not None:
                self._pricing_model = run.pricing_info.pricing_model

                if run.pricing_info.pricing_model == 'PAY_PER_EVENT':
                    for event_name, event_pricing in run.pricing_info.pricing_per_event.actor_charge_events.items():
                        self._pricing_info[event_name] = PricingInfoItem(
                            price=event_pricing.event_price_usd,
                            title=event_pricing.event_title,
                        )

                    self._max_total_charge_usd = run.options.max_total_charge_usd or self._max_total_charge_usd

            for event_name, count in (run.charged_event_counts or {}).items():
                price = self._pricing_info.get(event_name, PricingInfoItem(Decimal(), title='')).price
                self._charging_state[event_name] = ChargingStateItem(
                    charge_count=count,
                    total_charged_amount=count * price,
                )

        if not self._is_at_home and self._pricing_model == 'PAY_PER_EVENT':
            # We are not running on the Apify platform, but PPE is enabled for testing - open a dataset that
            # will contain a log of all charge calls for debugging purposes.

            if self._purge_charging_log_dataset:
                dataset = await Dataset.open(name=self.LOCAL_CHARGING_LOG_DATASET_NAME)
                await dataset.drop()

            self._charging_log_dataset = await Dataset.open(name=self.LOCAL_CHARGING_LOG_DATASET_NAME)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        if not self.active:
            raise RuntimeError('Exiting an uninitialized ChargingManager')

        self.active = False

    @ensure_context
    async def charge(self, event_name: str, count: int = 1) -> ChargeResult:
        def calculate_chargeable() -> dict[str, int | None]:
            """Calculate the maximum number of events of each type that can be charged within the current budget."""
            return {
                event_name: self.calculate_max_event_charge_count_within_limit(event_name)
                for event_name in self._pricing_info
            }

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
                chargeable_within_limit=calculate_chargeable(),
            )

        # START OF CRITICAL SECTION - no awaits here

        # Determine the maximum amount of events that can be charged within the budget
        charged_count = min(count, self.calculate_max_event_charge_count_within_limit(event_name) or count)

        if charged_count == 0:
            return ChargeResult(
                event_charge_limit_reached=True,
                charged_count=0,
                chargeable_within_limit=calculate_chargeable(),
            )

        pricing_info = self._pricing_info.get(
            event_name,
            PricingInfoItem(
                price=Decimal()
                if self._is_at_home
                else Decimal(
                    '1'
                ),  # Use a nonzero price for local development so that the maximum budget can be reached,
                title=f"Unknown event '{event_name}'",
            ),
        )

        # Update the charging state
        self._charging_state.setdefault(event_name, ChargingStateItem(0, Decimal()))
        self._charging_state[event_name].charge_count += charged_count
        self._charging_state[event_name].total_charged_amount += charged_count * pricing_info.price

        # END OF CRITICAL SECTION

        # If running on the platform, call the charge endpoint
        if self._is_at_home:
            if self._actor_run_id is None:
                raise RuntimeError('Actor run ID not configured')

            if event_name in self._pricing_info:
                await self._client.run(self._actor_run_id).charge(event_name, charged_count)
            else:
                logger.warning(f"Attempting to charge for an unknown event '{event_name}'")

        # Log the charged operation (if enabled)
        if self._charging_log_dataset:
            await self._charging_log_dataset.push_data(
                {
                    'event_name': event_name,
                    'event_title': pricing_info.title,
                    'event_price_usd': round(pricing_info.price, 3),
                    'charged_count': charged_count,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                }
            )

        # If it is not possible to charge the full amount, log that fact
        if charged_count < count:
            subject = 'instance' if count == 1 else 'instances'
            logger.info(
                f"Charging {count} ${subject} of '{event_name}' event would exceed max_total_charge_usd "
                '- only {charged_count} events were charged'
            )

        max_charge_count = self.calculate_max_event_charge_count_within_limit(event_name)

        return ChargeResult(
            event_charge_limit_reached=max_charge_count is not None and max_charge_count <= 0,
            charged_count=charged_count,
            chargeable_within_limit=calculate_chargeable(),
        )

    @ensure_context
    def calculate_total_charged_amount(self) -> Decimal:
        return sum(
            (item.total_charged_amount for item in self._charging_state.values()),
            start=Decimal(),
        )

    @ensure_context
    def calculate_max_event_charge_count_within_limit(self, event_name: str) -> int | None:
        pricing_info = self._pricing_info.get(event_name)

        if pricing_info is not None:
            price = pricing_info.price
        elif not self._is_at_home:
            price = Decimal('1')  # Use a nonzero price for local development so that the maximum budget can be reached
        else:
            price = Decimal()

        if not price:
            return None

        result = (self._max_total_charge_usd - self.calculate_total_charged_amount()) / price
        return math.floor(result) if result.is_finite() else None

    @ensure_context
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


@dataclass
class ChargingStateItem:
    charge_count: int
    total_charged_amount: Decimal


@dataclass
class PricingInfoItem:
    price: Decimal
    title: str
