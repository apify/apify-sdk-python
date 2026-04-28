import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import NamedTuple
from unittest.mock import AsyncMock, Mock, patch

from apify_client._models_generated import PayPerEventActorPricingInfo

from apify import Actor, Configuration
from apify._charging import ChargingManagerImplementation, PricingInfoItem


class MockedChargingSetup(NamedTuple):
    """Container for mocked charging components."""

    charging_mgr: ChargingManagerImplementation
    mock_charge: AsyncMock
    mock_client: Mock


@asynccontextmanager
async def setup_mocked_charging(
    configuration: Configuration, pricing_info: dict[str, Decimal]
) -> AsyncGenerator[MockedChargingSetup]:
    """Context manager that sets up an Actor with mocked charging on Apify platform.

    Usage:
        configuration = Configuration( max_total_charge_usd=Decimal('1.5'), test_pay_per_event=True)
        pricing_info = {'event': Decimal('1.0')}
        async with setup_mocked_charging(configuration, pricing_info) as setup:
            # Add pricing info for events
            setup.charging_mgr._pricing_info['event'] = PricingInfoItem(Decimal('1.0'), 'Event')

            result = await Actor.charge('event', count=1)
            setup.mock_charge.assert_called_once_with('event', count=1)
    """
    # Mock the ApifyClientAsync
    mock_client = Mock()
    mock_run_client = Mock()
    mock_charge = AsyncMock()

    mock_run_client.charge = mock_charge
    mock_client.run = Mock(return_value=mock_run_client)

    async with Actor(configuration):
        charging_mgr_impl = Actor.get_charging_manager()

        # Patch the charging manager to simulate running on Apify platform
        with (
            patch.object(charging_mgr_impl, '_is_at_home', new=True),
            patch.object(charging_mgr_impl, '_actor_run_id', 'test-run-id'),
            patch.object(charging_mgr_impl, '_client', mock_client),
        ):
            setup = MockedChargingSetup(
                charging_mgr=charging_mgr_impl,  # ty: ignore[invalid-argument-type]
                mock_charge=mock_charge,
                mock_client=mock_client,
            )

            for event_name, price in pricing_info.items():
                setup.charging_mgr._pricing_info[event_name] = PricingInfoItem(price, title=event_name.title())

            yield setup


async def test_actor_charge_push_data_with_no_remaining_budget() -> None:
    """Test that the API client is NOT called when budget is exhausted during push_data.

    When push_data can't afford to charge for any items, it correctly avoids calling the API.
    """
    async with setup_mocked_charging(
        Configuration(max_total_charge_usd=Decimal('1.5'), test_pay_per_event=True),
        {'some-event': Decimal('1.0'), 'another-event': Decimal('1.0')},
    ) as setup:
        # Exhaust most of the budget (events cost $1 each)
        result1 = await Actor.charge('some-event', count=1)  # Costs $1, leaving $0.5

        # Verify the first charge call was made correctly
        setup.mock_charge.assert_called_once_with('some-event', count=1)
        setup.mock_charge.reset_mock()

        assert result1.charged_count == 1

        # Now try to push data - we can't afford even 1 more event
        # This will call charge(event_name, count=0) because max_charged_count=0
        result = await Actor.push_data([{'hello': 'world'} for _ in range(10)], 'another-event')

        # The API should NOT be called when count=0
        setup.mock_charge.assert_not_called()

        # Correctly returns result with charged_count=0
        assert result is not None
        assert result.charged_count == 0
        assert result.event_charge_limit_reached is True

        # Verify no items were pushed
        dataset = await Actor.open_dataset()
        items = await dataset.get_data()
        assert len(items.items) == 0


async def test_actor_charge_api_call_verification() -> None:
    """Verify that charge() makes API calls correctly."""
    async with setup_mocked_charging(
        Configuration(max_total_charge_usd=Decimal('10.0'), test_pay_per_event=True), {'test-event': Decimal('1.0')}
    ) as setup:
        # Call charge directly with count=0 - this should NOT call the API
        result1 = await Actor.charge('test-event', count=0)
        setup.mock_charge.assert_not_called()
        assert result1.charged_count == 0

        # Call charge with count=1 - this SHOULD call the API
        result2 = await Actor.charge('test-event', count=1)
        setup.mock_charge.assert_called_once_with('test-event', count=1)
        assert result2.charged_count == 1


async def test_max_event_charge_count_within_limit_tolerates_overdraw() -> None:
    """Test that calculate_max_event_charge_count_within_limit does not return nonsensical (e.g., negative) values when
    the total number of charged events overdraws the max_total_charge_usd limit."""

    configuration = Configuration(
        max_total_charge_usd=Decimal('0.00025'),
        actor_pricing_info=PayPerEventActorPricingInfo.model_validate(
            {
                'pricingModel': 'PAY_PER_EVENT',
                'apifyMarginPercentage': 0.0,
                'createdAt': '2024-01-01T00:00:00.000Z',
                'startedAt': '2024-01-01T00:00:00.000Z',
                'pricingPerEvent': {
                    'actorChargeEvents': {
                        'event': {
                            'eventPriceUsd': 0.0003,
                            'eventTitle': 'Event',
                            'eventDescription': 'Event description',
                        },
                        'apify-actor-start': {
                            'eventPriceUsd': 0.00005,
                            'eventTitle': 'Actor start',
                            'eventDescription': 'Actor start description',
                        },
                    }
                },
            }
        ),
        charged_event_counts={'event': 1, 'apify-actor-start': 1},  # Already charged 2 events worth $0.00035
        test_pay_per_event=True,
    )

    async with setup_mocked_charging(configuration, {}) as setup:
        max_count = setup.charging_mgr.calculate_max_event_charge_count_within_limit('event')
        assert max_count == 0


async def test_push_data_combined_price_limits_items() -> None:
    """Test that push_data limits items when the combined explicit + synthetic event price exceeds the budget."""
    async with setup_mocked_charging(
        Configuration(max_total_charge_usd=Decimal('3.00'), test_pay_per_event=True),
        {'scrape': Decimal('1.00'), 'apify-default-dataset-item': Decimal('1.00')},
    ):
        data = [{'id': i} for i in range(5)]
        result = await Actor.push_data(data, 'scrape')

        assert result is not None
        assert result.charged_count == 1

        dataset = await Actor.open_dataset()
        items = await dataset.get_data()
        assert len(items.items) == 1
        assert items.items[0] == {'id': 0}


async def test_push_data_charges_synthetic_event_for_default_dataset() -> None:
    """Test that push_data charges both the explicit event and the synthetic apify-default-dataset-item event."""
    async with setup_mocked_charging(
        Configuration(max_total_charge_usd=Decimal('10.00'), test_pay_per_event=True),
        {'test': Decimal('0.10'), 'apify-default-dataset-item': Decimal('0.05')},
    ) as setup:
        data = [{'id': i} for i in range(3)]
        result = await Actor.push_data(data, 'test')

        assert result is not None
        assert result.charged_count == 3

        # Both explicit and synthetic events should be charged
        assert setup.charging_mgr.get_charged_event_count('test') == 3
        assert setup.charging_mgr.get_charged_event_count('apify-default-dataset-item') == 3


async def test_charge_lock_concurrent_actor_and_dataset_push() -> None:
    """Test that charge_lock properly synchronizes concurrent Actor.push_data and dataset.push_data calls."""
    async with setup_mocked_charging(
        Configuration(max_total_charge_usd=Decimal('10.00'), test_pay_per_event=True),
        {'event': Decimal('0.10'), 'apify-default-dataset-item': Decimal('0.10')},
    ) as setup:
        dataset = await Actor.open_dataset()

        # Run concurrent pushes - Actor.push_data and direct dataset.push_data
        await asyncio.gather(
            Actor.push_data([{'source': 'actor', 'id': i} for i in range(5)], 'event'),
            dataset.push_data([{'source': 'dataset', 'id': i} for i in range(5)]),
        )

        # Verify all items were pushed
        items = await dataset.get_data()
        assert len(items.items) == 10

        # Verify charging was tracked correctly:
        # - Actor.push_data charged 'event' (5) + 'apify-default-dataset-item' (5)
        # - dataset.push_data charged 'apify-default-dataset-item' (5)
        assert setup.charging_mgr.get_charged_event_count('event') == 5
        assert setup.charging_mgr.get_charged_event_count('apify-default-dataset-item') == 10


async def test_charge_lock_concurrent_with_limited_budget() -> None:
    """Test that charge_lock correctly limits items when concurrent pushes compete for limited budget."""
    async with setup_mocked_charging(
        Configuration(max_total_charge_usd=Decimal('0.50'), test_pay_per_event=True),
        {'apify-default-dataset-item': Decimal('0.10')},
    ) as setup:
        dataset = await Actor.open_dataset()

        # Both try to push 5 items, but budget only allows 5 total
        await asyncio.gather(
            dataset.push_data([{'source': 'a', 'id': i} for i in range(5)]),
            dataset.push_data([{'source': 'b', 'id': i} for i in range(5)]),
        )

        # Verify total items pushed does not exceed budget limit
        items = await dataset.get_data()
        assert len(items.items) == 5  # Budget allows max 5 items at $0.10 each

        # Verify total charged events matches items pushed
        assert setup.charging_mgr.get_charged_event_count('apify-default-dataset-item') == 5


async def test_charge_with_overdrawn_budget() -> None:
    configuration = Configuration(
        max_total_charge_usd=Decimal('0.00025'),
        actor_pricing_info=PayPerEventActorPricingInfo.model_validate(
            {
                'pricingModel': 'PAY_PER_EVENT',
                'apifyMarginPercentage': 0.0,
                'createdAt': '2024-01-01T00:00:00.000Z',
                'startedAt': '2024-01-01T00:00:00.000Z',
                'pricingPerEvent': {
                    'actorChargeEvents': {
                        'event': {
                            'eventPriceUsd': 0.0003,
                            'eventTitle': 'Event',
                            'eventDescription': 'Event description',
                        },
                        'apify-actor-start': {
                            'eventPriceUsd': 0.00005,
                            'eventTitle': 'Actor start',
                            'eventDescription': 'Actor start description',
                        },
                    }
                },
            }
        ),
        charged_event_counts={'event': 0, 'apify-actor-start': 1},
        test_pay_per_event=True,
    )

    async with setup_mocked_charging(configuration, {}) as setup:
        charge_result = await Actor.charge('event', 1)
        assert charge_result.charged_count == 0  # The budget doesn't allow another event

        push_result = await Actor.push_data([{'hello': 'world'}], 'event')
        assert push_result.charged_count == 0  # Nor does the budget allow this

        setup.mock_charge.assert_not_called()
