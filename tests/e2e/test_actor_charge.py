from __future__ import annotations

from decimal import Decimal
from functools import partial
from typing import TYPE_CHECKING

import pytest_asyncio

from .._utils import poll_until_condition
from apify import Actor

if TYPE_CHECKING:
    from apify_client import ApifyClientAsync
    from apify_client._models import Run
    from apify_client._resource_clients import ActorClientAsync

    from .conftest import MakeActorFunction, RunActorFunction


async def _get_run(apify_client_async: ApifyClientAsync, run_id: str) -> Run:
    """Fetch the current state of the given run from the platform."""
    run = await apify_client_async.run(run_id).get()
    assert run is not None
    return run


@pytest_asyncio.fixture(scope='module', loop_scope='module')
async def ppe_push_data_actor_build(make_actor: MakeActorFunction) -> str:
    async def main() -> None:
        async with Actor:
            await Actor.push_data(
                [{'id': i} for i in range(5)],
                charged_event_name='push-item',
            )

    actor_client = await make_actor('ppe-push-data', main_func=main)

    await actor_client.update(
        pricing_infos=[
            {
                'pricingModel': 'PAY_PER_EVENT',
                'apifyMarginPercentage': 0.0,
                'createdAt': '2024-01-01T00:00:00.000Z',
                'startedAt': '2024-01-01T00:00:00.000Z',
                'pricingPerEvent': {
                    'actorChargeEvents': {
                        'push-item': {
                            'eventTitle': 'Push item',
                            'eventPriceUsd': 0.05,
                            'eventDescription': 'One pushed item',
                        },
                        'apify-default-dataset-item': {
                            'eventTitle': 'Default dataset item',
                            'eventPriceUsd': 0.05,
                            'eventDescription': 'One item written to the default dataset',
                        },
                    },
                },
            },
        ]
    )

    actor = await actor_client.get()

    assert actor is not None
    return actor.id


@pytest_asyncio.fixture(scope='function', loop_scope='module')
async def ppe_push_data_actor(
    ppe_push_data_actor_build: str,
    apify_client_async: ApifyClientAsync,
) -> ActorClientAsync:
    return apify_client_async.actor(ppe_push_data_actor_build)


@pytest_asyncio.fixture(scope='module', loop_scope='module')
async def ppe_actor_build(make_actor: MakeActorFunction) -> str:
    async def main() -> None:
        import asyncio
        from dataclasses import asdict

        async with Actor:
            charge_result = await Actor.charge(
                event_name='foobar',
                count=4,
            )
            Actor.log.info('Charged', extra=asdict(charge_result))

            # When the charge limit is reached, the platform auto-aborts this run. A background daemon enforces the
            # limit, usually within seconds but sometimes far later. Give the abort time to arrive, but exit on our
            # own afterwards, so a slow daemon can't hold the run until its timeout.
            if charge_result.event_charge_limit_reached:
                await asyncio.sleep(60)

    actor_client = await make_actor('ppe', main_func=main)

    await actor_client.update(
        pricing_infos=[
            {
                'pricingModel': 'PAY_PER_EVENT',
                'apifyMarginPercentage': 0.0,
                'createdAt': '2024-01-01T00:00:00.000Z',
                'startedAt': '2024-01-01T00:00:00.000Z',
                'pricingPerEvent': {
                    'actorChargeEvents': {
                        'foobar': {
                            'eventTitle': 'Foo bar',
                            'eventPriceUsd': 0.1,
                            'eventDescription': 'Foo foo bar bar',
                        },
                    },
                },
            },
        ],
    )

    actor = await actor_client.get()

    assert actor is not None
    return str(actor.id)


@pytest_asyncio.fixture(scope='function', loop_scope='module')
async def ppe_actor(
    ppe_actor_build: str,
    apify_client_async: ApifyClientAsync,
) -> ActorClientAsync:
    return apify_client_async.actor(ppe_actor_build)


async def test_actor_charge_basic(
    ppe_actor: ActorClientAsync,
    run_actor: RunActorFunction,
    apify_client_async: ApifyClientAsync,
) -> None:
    run = await run_actor(ppe_actor)

    # Refetch until the charged event counts propagate on the platform.
    run = await poll_until_condition(
        partial(_get_run, apify_client_async, run.id),
        lambda r: r.status == 'SUCCEEDED' and r.charged_event_counts == {'foobar': 4},
        timeout=30,
        poll_interval=1,
    )

    assert run.status == 'SUCCEEDED'
    assert run.charged_event_counts == {'foobar': 4}


async def test_actor_charge_limit(
    ppe_actor: ActorClientAsync,
    run_actor: RunActorFunction,
    apify_client_async: ApifyClientAsync,
) -> None:
    run = await run_actor(ppe_actor, max_total_charge_usd=Decimal('0.2'))

    # The Actor charges 4 events and the budget covers 2, so the SDK charges 3 - one over the budget, which makes
    # the platform auto-abort the run. The Actor waits for the abort (see `ppe_actor_build`), so the run usually
    # ends as ABORTED, or as SUCCEEDED when the platform enforces the limit late.
    assert run.status in ('ABORTED', 'SUCCEEDED')

    # Refetch until the charged event counts propagate on the platform.
    run = await poll_until_condition(
        partial(_get_run, apify_client_async, run.id),
        lambda r: r.charged_event_counts == {'foobar': 3},
        timeout=30,
        poll_interval=1,
    )

    assert run.charged_event_counts == {'foobar': 3}


async def test_actor_push_data_charges_both_events(
    ppe_push_data_actor: ActorClientAsync,
    run_actor: RunActorFunction,
    apify_client_async: ApifyClientAsync,
) -> None:
    """Test that push_data charges both the explicit event and the synthetic apify-default-dataset-item event."""
    run = await run_actor(ppe_push_data_actor)

    expected_counts = {
        'push-item': 5,
        'apify-default-dataset-item': 5,
    }

    # Use a longer timeout for synthetic events like `apify-default-dataset-item`: the platform computes them
    # from dataset writes asynchronously, so they propagate more slowly than explicit charges (which are
    # reflected immediately via the charge endpoint).
    run = await poll_until_condition(
        partial(_get_run, apify_client_async, run.id),
        lambda r: r.status == 'SUCCEEDED' and r.charged_event_counts == expected_counts,
        timeout=120,
        poll_interval=1,
    )

    assert run.status == 'SUCCEEDED'
    assert run.charged_event_counts == expected_counts


async def test_actor_push_data_combined_budget_limit(
    ppe_push_data_actor: ActorClientAsync,
    run_actor: RunActorFunction,
    apify_client_async: ApifyClientAsync,
) -> None:
    """Test that push_data respects combined budget: explicit ($0.05) + synthetic ($0.05) = $0.10/item.

    With max_total_charge_usd=$0.20, only 2 of 5 items fit in the budget.
    """
    run = await run_actor(ppe_push_data_actor, max_total_charge_usd=Decimal('0.20'))

    expected_counts = {
        'push-item': 2,
        'apify-default-dataset-item': 2,
    }

    # Use a longer timeout for synthetic events like `apify-default-dataset-item`: the platform computes them
    # from dataset writes asynchronously, so they propagate more slowly than explicit charges (which are
    # reflected immediately via the charge endpoint).
    run = await poll_until_condition(
        partial(_get_run, apify_client_async, run.id),
        lambda r: r.status == 'SUCCEEDED' and r.charged_event_counts == expected_counts,
        timeout=120,
        poll_interval=1,
    )

    assert run.status == 'SUCCEEDED'
    assert run.charged_event_counts == expected_counts


@pytest_asyncio.fixture(scope='module', loop_scope='module')
async def ppe_reboot_actor_build(make_actor: MakeActorFunction) -> str:
    async def main() -> None:
        async with Actor:
            key_value_store = await Actor.open_key_value_store()
            charging_manager = Actor.get_charging_manager()

            if not await key_value_store.get_value('REBOOTED'):
                for _ in range(3):
                    await Actor.charge('row-charged')
                await key_value_store.set_value('REBOOTED', {'rebooted': True})
                await Actor.reboot()
                return

            # The second container starts from the counts the platform recorded when the run started. The first
            # charge loads the run's current counts, so the view recorded afterwards includes the earlier charges.
            charge_result = await Actor.charge('row-charged')
            await key_value_store.set_value(
                'SDK_VIEW_AFTER_REBOOT',
                {
                    'chargedCount': charging_manager.get_charged_event_count('row-charged'),
                    'totalChargedUsd': str(charging_manager.calculate_total_charged_amount()),
                    'chargeableWithinLimit': charge_result.chargeable_within_limit['row-charged'],
                },
            )

    actor_client = await make_actor('ppe-reboot', main_func=main)

    await actor_client.update(
        pricing_infos=[
            {
                'pricingModel': 'PAY_PER_EVENT',
                'apifyMarginPercentage': 0.0,
                'createdAt': '2024-01-01T00:00:00.000Z',
                'startedAt': '2024-01-01T00:00:00.000Z',
                'pricingPerEvent': {
                    'actorChargeEvents': {
                        'row-charged': {
                            'eventTitle': 'Row charged',
                            'eventPriceUsd': 0.005,
                            'eventDescription': 'One charged row',
                        },
                    },
                },
            },
        ],
    )

    actor = await actor_client.get()

    assert actor is not None
    return actor.id


@pytest_asyncio.fixture(scope='function', loop_scope='module')
async def ppe_reboot_actor(
    ppe_reboot_actor_build: str,
    apify_client_async: ApifyClientAsync,
) -> ActorClientAsync:
    return apify_client_async.actor(ppe_reboot_actor_build)


async def test_actor_charge_counts_survive_reboot(
    ppe_reboot_actor: ActorClientAsync,
    run_actor: RunActorFunction,
    apify_client_async: ApifyClientAsync,
) -> None:
    """Test that a rebooted run continues from the events charged before the reboot, instead of a fresh budget."""
    run = await run_actor(ppe_reboot_actor, max_total_charge_usd=Decimal('0.05'))

    assert run.status == 'SUCCEEDED'
    assert run.stats.reboot_count == 1

    # Refetch until the charged event counts propagate on the platform.
    run = await poll_until_condition(
        partial(_get_run, apify_client_async, run.id),
        lambda r: r.charged_event_counts == {'row-charged': 4},
        timeout=30,
        poll_interval=1,
    )
    assert run.charged_event_counts == {'row-charged': 4}

    record = await apify_client_async.key_value_store(run.default_key_value_store_id).get_record(
        'SDK_VIEW_AFTER_REBOOT'
    )
    assert record is not None

    # Three events were charged before the reboot and one after it. The budget of $0.05 at $0.005 per event leaves
    # room for six more.
    assert record['value'] == {
        'chargedCount': 4,
        'totalChargedUsd': '0.020',
        'chargeableWithinLimit': 6,
    }
