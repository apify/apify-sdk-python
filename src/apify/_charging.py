from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Union

from pydantic import TypeAdapter

from apify._models import ActorRun, PricingModel
from apify.log import logger
from apify.storages import Dataset

if TYPE_CHECKING:
    from apify_client import ApifyClientAsync

    from apify._configuration import Configuration


run_validator: TypeAdapter[ActorRun | None] = TypeAdapter(Union[ActorRun, None])


class ChargingManager:
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

        self._charging_state: dict[str, ChargingStateItem] | None = None
        self._pricing_info: dict[str, PricingInfoItem] = {}

        self._not_ppe_warning_printed = False

    async def init(self) -> None:
        self._charging_state = {}

        if self._is_at_home:
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
            if self._purge_charging_log_dataset:
                dataset = await Dataset.open(name=self.LOCAL_CHARGING_LOG_DATASET_NAME)
                await dataset.drop()

            self._charging_log_dataset = await Dataset.open(name=self.LOCAL_CHARGING_LOG_DATASET_NAME)

    async def charge(self, event_name: str, count: int = 1) -> ChargeResult:
        if self._charging_state is None:
            raise RuntimeError('Charging manager is not initialized')

        def calculate_chargeable() -> dict[str, int | None]:
            return {
                event_name: self.calculate_max_event_charge_count_within_limit(event_name)
                for event_name in self._pricing_info
            }

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

        self._charging_state.setdefault(event_name, ChargingStateItem(0, Decimal()))
        self._charging_state[event_name].charge_count += charged_count
        self._charging_state[event_name].total_charged_amount += charged_count * pricing_info.price

        # END OF CRITICAL SECTION
        if self._is_at_home:
            if self._actor_run_id is None:
                raise RuntimeError('Actor run ID not configured')

            if event_name is self._pricing_info:
                await self._client.run(self._actor_run_id).charge(event_name, charged_count)
            else:
                logger.warning(f"Attempting to charge for an unknown event '{event_name}'")

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

    def calculate_total_charged_amount(self) -> Decimal:
        if self._charging_state is None:
            raise RuntimeError('Charging manager is not initialized')

        return sum(
            (item.total_charged_amount for item in self._charging_state.values()),
            start=Decimal(),
        )

    def calculate_max_event_charge_count_within_limit(self, event_name: str) -> int | None:
        if self._charging_state is None:
            raise RuntimeError('Charging manager is not initialized')

        pricing_info = self._pricing_info.get(event_name)

        if pricing_info is not None:
            price = pricing_info.price
        elif not self._is_at_home:
            price = Decimal('1')  # Use a nonzero price for local development so that the maximum budget can be reached
        else:
            price = Decimal()

        if not price:
            return None

        return math.floor((self._max_total_charge_usd - self.calculate_total_charged_amount()) / price)

    def get_pricing_info(self) -> ActorPricingInfo:
        if self._charging_state is None:
            raise RuntimeError('Charging manager is not initialized')

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


@dataclass(frozen=True)
class ChargeResult:
    event_charge_limit_reached: bool
    charged_count: int
    chargeable_within_limit: dict[str, int | None]


@dataclass
class ChargingStateItem:
    charge_count: int
    total_charged_amount: Decimal


@dataclass
class PricingInfoItem:
    price: Decimal
    title: str


@dataclass
class ActorPricingInfo:
    pricing_model: PricingModel | None
    max_total_charge_usd: Decimal
    is_pay_per_event: bool
    per_event_prices: dict[str, Decimal]
