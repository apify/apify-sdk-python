from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from apify._models import (
    ActorRun,
    FlatPricePerMonthActorPricingInfo,
    FreeActorPricingInfo,
    PayPerEventActorPricingInfo,
    PricePerDatasetItemActorPricingInfo,
)

_MINIMAL_RUN_DICT = {
    'id': 'run-123',
    'actId': 'act-456',
    'userId': 'user-789',
    'startedAt': '2024-01-01T00:00:00Z',
    'status': 'SUCCEEDED',
    'meta': {'origin': 'API'},
    'stats': {
        'restartCount': 0,
        'resurrectCount': 0,
        'computeUnits': 0.5,
    },
    'options': {
        'build': 'latest',
        'timeoutSecs': 300,
        'memoryMbytes': 1024,
        'diskMbytes': 2048,
    },
    'buildId': 'build-abc',
    'defaultKeyValueStoreId': 'kvs-def',
    'defaultDatasetId': 'ds-ghi',
    'defaultRequestQueueId': 'rq-jkl',
    'containerUrl': 'http://localhost:4321',
}


def test_actor_run_from_dict() -> None:
    """Test ActorRun model can be created from a dict with aliased fields."""
    run = ActorRun.model_validate(_MINIMAL_RUN_DICT)
    assert run.id == 'run-123'
    assert run.act_id == 'act-456'
    assert run.user_id == 'user-789'
    assert run.status == 'SUCCEEDED'
    assert run.stats.restart_count == 0
    assert run.options.build == 'latest'
    assert run.default_dataset_id == 'ds-ghi'


def test_actor_run_optional_fields_missing() -> None:
    """Test ActorRun with optional fields missing."""
    run = ActorRun.model_validate(_MINIMAL_RUN_DICT)
    assert run.finished_at is None
    assert run.exit_code is None
    assert run.usage is None
    assert run.pricing_info is None
    assert run.charged_event_counts is None
    assert run.actor_task_id is None
    assert run.build_number is None
    assert run.git_branch_name is None


def test_pricing_model_discriminated_union() -> None:
    """Test that pricing_info discriminated union works for all pricing models."""
    # FREE model
    run_data = {**_MINIMAL_RUN_DICT, 'pricingInfo': {'pricingModel': 'FREE'}}
    run = ActorRun.model_validate(run_data)
    assert isinstance(run.pricing_info, FreeActorPricingInfo)
    assert run.pricing_info.pricing_model == 'FREE'

    # FLAT_PRICE_PER_MONTH model
    run_data = {
        **_MINIMAL_RUN_DICT,
        'pricingInfo': {'pricingModel': 'FLAT_PRICE_PER_MONTH', 'pricePerUnitUsd': '9.99'},
    }
    run = ActorRun.model_validate(run_data)
    assert isinstance(run.pricing_info, FlatPricePerMonthActorPricingInfo)
    assert run.pricing_info.price_per_unit_usd == Decimal('9.99')

    # PRICE_PER_DATASET_ITEM model
    run_data = {
        **_MINIMAL_RUN_DICT,
        'pricingInfo': {'pricingModel': 'PRICE_PER_DATASET_ITEM', 'pricePerUnitUsd': '0.01'},
    }
    run = ActorRun.model_validate(run_data)
    assert isinstance(run.pricing_info, PricePerDatasetItemActorPricingInfo)

    # PAY_PER_EVENT model
    run_data = {
        **_MINIMAL_RUN_DICT,
        'pricingInfo': {
            'pricingModel': 'PAY_PER_EVENT',
            'pricingPerEvent': {
                'actorChargeEvents': {
                    'search': {'eventPriceUsd': '0.05', 'eventTitle': 'Search'},
                },
            },
        },
    }
    run = ActorRun.model_validate(run_data)
    assert isinstance(run.pricing_info, PayPerEventActorPricingInfo)
    assert 'search' in run.pricing_info.pricing_per_event.actor_charge_events
    assert run.pricing_info.pricing_per_event.actor_charge_events['search'].event_price_usd == Decimal('0.05')


def test_actor_run_invalid_data() -> None:
    """Test that ActorRun raises validation error with invalid data."""
    with pytest.raises(ValidationError):
        ActorRun.model_validate({'id': 'run-123'})  # Missing required fields
