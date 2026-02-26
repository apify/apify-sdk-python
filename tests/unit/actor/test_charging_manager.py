from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from apify._charging import ChargingManagerImplementation
from apify._configuration import Configuration
from apify._models import (
    ActorChargeEvent,
    PayPerEventActorPricingInfo,
)


def _make_config(**kwargs: Any) -> Configuration:
    """Helper to create a Configuration with sensible defaults for charging tests.

    Note: Some Configuration fields have BeforeValidators that convert falsy values to None
    (e.g. charged_event_counts={} -> None). We bypass this by setting such fields directly
    on the constructed object after initialization.
    """
    # Fields that need to be set directly to bypass BeforeValidator(lambda data: data or None)
    post_init_fields = {}
    for field_name in ('actor_pricing_info', 'charged_event_counts'):
        if field_name in kwargs:
            post_init_fields[field_name] = kwargs.pop(field_name)

    defaults: dict[str, Any] = {
        'is_at_home': False,
        'actor_run_id': None,
        'max_total_charge_usd': None,
        'purge_on_start': False,
        'test_pay_per_event': False,
    }
    defaults.update(kwargs)
    config = Configuration(**defaults)

    # Set fields that would be mangled by validators
    for field_name, value in post_init_fields.items():
        object.__setattr__(config, field_name, value)

    return config


def _make_ppe_pricing_info(events: dict[str, Decimal] | None = None) -> PayPerEventActorPricingInfo:
    """Helper to create PayPerEventActorPricingInfo."""
    if events is None:
        events = {'search': Decimal('0.01'), 'scrape': Decimal('0.05')}
    charge_events = {
        name: ActorChargeEvent.model_validate({'eventPriceUsd': price, 'eventTitle': f'{name} event'})
        for name, price in events.items()
    }
    return PayPerEventActorPricingInfo.model_validate(
        {
            'pricingModel': 'PAY_PER_EVENT',
            'pricingPerEvent': {
                'actorChargeEvents': {name: event.model_dump(by_alias=True) for name, event in charge_events.items()}
            },
        }
    )


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock()
    client.run = MagicMock(return_value=MagicMock(get=AsyncMock(return_value=None), charge=AsyncMock()))
    return client


async def test_charge_without_ppe_model_prints_warning(
    mock_client: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that charging without PPE model logs a warning and returns zero charged_count."""
    config = _make_config(
        actor_pricing_info=None,
        charged_event_counts={},
    )
    cm = ChargingManagerImplementation(config, mock_client)
    async with cm:
        result = await cm.charge('search', count=1)
        assert result.charged_count == 0
        assert result.event_charge_limit_reached is False
        assert 'does not use the pay-per-event pricing' in caplog.text


async def test_charge_without_ppe_warning_printed_once(
    mock_client: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that the not-PPE warning is printed only once."""
    config = _make_config(actor_pricing_info=None, charged_event_counts={})
    cm = ChargingManagerImplementation(config, mock_client)
    async with cm:
        await cm.charge('search', count=1)
        await cm.charge('search', count=1)
    assert caplog.text.count('does not use the pay-per-event pricing') == 1


async def test_charge_known_event_locally(mock_client: MagicMock) -> None:
    """Test charging a known event in local PPE mode."""
    pricing_info = _make_ppe_pricing_info({'search': Decimal('0.01')})
    config = _make_config(
        test_pay_per_event=True,
        actor_pricing_info=pricing_info,
        charged_event_counts={},
        max_total_charge_usd=Decimal('10.00'),
    )
    cm = ChargingManagerImplementation(config, mock_client)
    async with cm:
        result = await cm.charge('search', count=5)
        assert result.charged_count == 5
        assert cm.get_charged_event_count('search') == 5


async def test_charge_partial_count_within_budget(mock_client: MagicMock) -> None:
    """Test that charging is capped when budget is insufficient for the full count."""
    pricing_info = _make_ppe_pricing_info({'search': Decimal('1.00')})
    config = _make_config(
        test_pay_per_event=True,
        actor_pricing_info=pricing_info,
        charged_event_counts={},
        max_total_charge_usd=Decimal('3.00'),
    )
    cm = ChargingManagerImplementation(config, mock_client)
    async with cm:
        result = await cm.charge('search', count=5)
        assert result.charged_count == 3
        # Budget is fully exhausted ($3.00 spent of $3.00), so limit is reached
        assert result.event_charge_limit_reached is True


async def test_charge_unknown_event_locally(
    mock_client: MagicMock,
) -> None:
    """Test charging an unknown event locally uses price of 1."""
    pricing_info = _make_ppe_pricing_info({'search': Decimal('0.01')})
    config = _make_config(
        test_pay_per_event=True,
        actor_pricing_info=pricing_info,
        charged_event_counts={},
        max_total_charge_usd=Decimal('10.00'),
    )
    cm = ChargingManagerImplementation(config, mock_client)
    async with cm:
        result = await cm.charge('unknown_event', count=1)
        assert result.charged_count == 1


async def test_calculate_total_charged_amount(mock_client: MagicMock) -> None:
    """Test total charged amount calculation."""
    pricing_info = _make_ppe_pricing_info({'search': Decimal('0.01'), 'scrape': Decimal('0.05')})
    config = _make_config(
        test_pay_per_event=True,
        actor_pricing_info=pricing_info,
        charged_event_counts={},
        max_total_charge_usd=Decimal('100.00'),
    )
    cm = ChargingManagerImplementation(config, mock_client)
    async with cm:
        await cm.charge('search', count=10)
        await cm.charge('scrape', count=2)
        total = cm.calculate_total_charged_amount()
        assert total == Decimal('0.10') + Decimal('0.10')  # 10*0.01 + 2*0.05


async def test_get_pricing_info_structure(mock_client: MagicMock) -> None:
    """Test get_pricing_info returns correct structure."""
    pricing_info = _make_ppe_pricing_info({'search': Decimal('0.01')})
    config = _make_config(
        test_pay_per_event=True,
        actor_pricing_info=pricing_info,
        charged_event_counts={},
        max_total_charge_usd=Decimal('10.00'),
    )
    cm = ChargingManagerImplementation(config, mock_client)
    async with cm:
        info = cm.get_pricing_info()
        assert info.is_pay_per_event is True
        assert info.pricing_model == 'PAY_PER_EVENT'
        assert info.max_total_charge_usd == Decimal('10.00')
        assert 'search' in info.per_event_prices
        assert info.per_event_prices['search'] == Decimal('0.01')


async def test_get_charged_event_count_unknown_event(mock_client: MagicMock) -> None:
    """Test get_charged_event_count returns 0 for unknown events."""
    config = _make_config(actor_pricing_info=None, charged_event_counts={})
    cm = ChargingManagerImplementation(config, mock_client)
    async with cm:
        assert cm.get_charged_event_count('nonexistent') == 0


async def test_fetch_pricing_from_env_vars(mock_client: MagicMock) -> None:
    """Test that pricing info is fetched from env vars when available."""
    pricing_info = _make_ppe_pricing_info({'search': Decimal('0.01')})
    config = _make_config(
        actor_pricing_info=pricing_info,
        charged_event_counts={'search': 5},
        max_total_charge_usd=Decimal('10.00'),
    )
    cm = ChargingManagerImplementation(config, mock_client)
    async with cm:
        assert cm.get_charged_event_count('search') == 5


async def test_fetch_pricing_local_without_env_vars(mock_client: MagicMock) -> None:
    """Test local development without pricing env vars returns no pricing model."""
    config = _make_config()
    cm = ChargingManagerImplementation(config, mock_client)
    async with cm:
        info = cm.get_pricing_info()
        assert info.pricing_model is None
        assert info.is_pay_per_event is False


async def test_aexit_without_aenter_raises(mock_client: MagicMock) -> None:
    """Test that exiting without entering raises RuntimeError."""
    config = _make_config()
    cm = ChargingManagerImplementation(config, mock_client)
    with pytest.raises(RuntimeError, match='Exiting an uninitialized ChargingManager'):
        await cm.__aexit__(None, None, None)


async def test_test_pay_per_event_at_home_raises(mock_client: MagicMock) -> None:
    """Test that test_pay_per_event at home raises ValueError."""
    config = _make_config(
        is_at_home=True,
        test_pay_per_event=True,
        actor_run_id='test-run-id',
    )
    cm = ChargingManagerImplementation(config, mock_client)
    with pytest.raises(ValueError, match='only supported in a local development environment'):
        async with cm:
            pass


async def test_get_max_total_charge_usd(mock_client: MagicMock) -> None:
    """Test get_max_total_charge_usd returns the configured value."""
    config = _make_config(
        max_total_charge_usd=Decimal('42.50'),
        actor_pricing_info=None,
        charged_event_counts={},
    )
    cm = ChargingManagerImplementation(config, mock_client)
    async with cm:
        assert cm.get_max_total_charge_usd() == Decimal('42.50')


async def test_calculate_push_data_limit_no_ppe(mock_client: MagicMock) -> None:
    """Returns items_count when no PPE pricing is configured (prices are zero)."""
    config = _make_config(actor_pricing_info=None, charged_event_counts={})
    cm = ChargingManagerImplementation(config, mock_client)
    async with cm:
        result = cm.calculate_push_data_limit(10, 'some-event', is_default_dataset=True)
        assert result == 10


async def test_calculate_push_data_limit_within_budget(mock_client: MagicMock) -> None:
    """Returns full items_count when combined budget is sufficient for all items."""
    pricing_info = _make_ppe_pricing_info({'click': Decimal('0.01'), 'apify-default-dataset-item': Decimal('0.01')})
    config = _make_config(
        test_pay_per_event=True,
        actor_pricing_info=pricing_info,
        charged_event_counts={},
        max_total_charge_usd=Decimal('10.00'),
    )
    cm = ChargingManagerImplementation(config, mock_client)
    async with cm:
        # combined price = 0.02/item, budget = 10.00, max = 500
        result = cm.calculate_push_data_limit(5, 'click', is_default_dataset=True)
        assert result == 5


async def test_calculate_push_data_limit_budget_exceeded(mock_client: MagicMock) -> None:
    """Returns capped count when combined price (explicit + synthetic) exceeds budget."""
    pricing_info = _make_ppe_pricing_info({'scrape': Decimal('1.00'), 'apify-default-dataset-item': Decimal('1.00')})
    config = _make_config(
        test_pay_per_event=True,
        actor_pricing_info=pricing_info,
        charged_event_counts={},
        max_total_charge_usd=Decimal('3.00'),
    )
    cm = ChargingManagerImplementation(config, mock_client)
    async with cm:
        # combined price = 2.00/item, budget = 3.00, max = floor(3/2) = 1
        result = cm.calculate_push_data_limit(5, 'scrape', is_default_dataset=True)
        assert result == 1


async def test_calculate_push_data_limit_without_default_dataset(mock_client: MagicMock) -> None:
    """When not pushing to the default dataset, only explicit event price is considered."""
    pricing_info = _make_ppe_pricing_info({'scrape': Decimal('1.00'), 'apify-default-dataset-item': Decimal('1.00')})
    config = _make_config(
        test_pay_per_event=True,
        actor_pricing_info=pricing_info,
        charged_event_counts={},
        max_total_charge_usd=Decimal('3.00'),
    )
    cm = ChargingManagerImplementation(config, mock_client)
    async with cm:
        # explicit price only = 1.00/item, budget = 3.00, max = floor(3/1) = 3
        result = cm.calculate_push_data_limit(5, 'scrape', is_default_dataset=False)
        assert result == 3


async def test_calculate_push_data_limit_exhausted_budget(mock_client: MagicMock) -> None:
    """Returns 0 when the budget is fully exhausted before the push."""
    pricing_info = _make_ppe_pricing_info({'scrape': Decimal('1.00')})
    config = _make_config(
        test_pay_per_event=True,
        actor_pricing_info=pricing_info,
        charged_event_counts={'scrape': 3},
        max_total_charge_usd=Decimal('3.00'),
    )
    cm = ChargingManagerImplementation(config, mock_client)
    async with cm:
        result = cm.calculate_push_data_limit(5, 'scrape', is_default_dataset=False)
        assert result == 0


async def test_charge_limit_reached(mock_client: MagicMock) -> None:
    """Test that event_charge_limit_reached is True when budget is exhausted."""
    pricing_info = _make_ppe_pricing_info({'search': Decimal('5.00')})
    config = _make_config(
        test_pay_per_event=True,
        actor_pricing_info=pricing_info,
        charged_event_counts={},
        max_total_charge_usd=Decimal('5.00'),
    )
    cm = ChargingManagerImplementation(config, mock_client)
    async with cm:
        result1 = await cm.charge('search', count=1)
        assert result1.charged_count == 1
        assert result1.event_charge_limit_reached is True

        result2 = await cm.charge('search', count=1)
        assert result2.charged_count == 0
        assert result2.event_charge_limit_reached is True
