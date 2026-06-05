from __future__ import annotations

from decimal import Decimal
from functools import partial
from typing import TYPE_CHECKING

import pytest_asyncio

from apify_shared.consts import ActorJobStatus

from .._utils import poll_until_condition
from apify import Actor
from apify._models import ActorRun

if TYPE_CHECKING:
    from apify_client import ApifyClientAsync
    from apify_client.clients import ActorClientAsync

    from .conftest import MakeActorFunction, RunActorFunction


async def _get_run(apify_client_async: ApifyClientAsync, run_id: str) -> ActorRun:
    """Fetch the current state of the given run from the platform."""
    return ActorRun.model_validate(await apify_client_async.run(run_id).get())


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
    return str(actor['id'])


@pytest_asyncio.fixture(scope='function', loop_scope='module')
async def ppe_push_data_actor(
    ppe_push_data_actor_build: str,
    apify_client_async: ApifyClientAsync,
) -> ActorClientAsync:
    return apify_client_async.actor(ppe_push_data_actor_build)


@pytest_asyncio.fixture(scope='module', loop_scope='module')
async def ppe_actor_build(make_actor: MakeActorFunction) -> str:
    async def main() -> None:
        from dataclasses import asdict

        async with Actor:
            charge_result = await Actor.charge(
                event_name='foobar',
                count=4,
            )
            Actor.log.info('Charged', extra=asdict(charge_result))

    actor_client = await make_actor('ppe', main_func=main)

    await actor_client.update(
        pricing_infos=[
            {
                'pricingModel': 'PAY_PER_EVENT',
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
        ]
    )

    actor = await actor_client.get()

    assert actor is not None
    return str(actor['id'])


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
        lambda r: r.status == ActorJobStatus.SUCCEEDED and r.charged_event_counts == {'foobar': 4},
        timeout=30,
        poll_interval=1,
    )

    assert run.status == ActorJobStatus.SUCCEEDED
    assert run.charged_event_counts == {'foobar': 4}


async def test_actor_charge_limit(
    ppe_actor: ActorClientAsync,
    run_actor: RunActorFunction,
    apify_client_async: ApifyClientAsync,
) -> None:
    run = await run_actor(ppe_actor, max_total_charge_usd=Decimal('0.2'))

    # Reaching `max_total_charge_usd` makes the platform abort the run automatically, and that abort races with the
    # Actor's own clean exit — so the terminal status is either SUCCEEDED or ABORTED. Both are valid here; the
    # behavior under test is that the charge limit capped the run at exactly 2 of the 4 attempted events.
    terminal_statuses = {ActorJobStatus.SUCCEEDED, ActorJobStatus.ABORTED}

    # Refetch until the charged event counts propagate on the platform.
    run = await poll_until_condition(
        partial(_get_run, apify_client_async, run.id),
        lambda r: r.status in terminal_statuses and r.charged_event_counts == {'foobar': 2},
        timeout=30,
        poll_interval=1,
    )

    assert run.status in terminal_statuses
    assert run.charged_event_counts == {'foobar': 2}


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
        lambda r: r.status == ActorJobStatus.SUCCEEDED and r.charged_event_counts == expected_counts,
        timeout=120,
        poll_interval=1,
    )

    assert run.status == ActorJobStatus.SUCCEEDED
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
        lambda r: r.status == ActorJobStatus.SUCCEEDED and r.charged_event_counts == expected_counts,
        timeout=120,
        poll_interval=1,
    )

    assert run.status == ActorJobStatus.SUCCEEDED
    assert run.charged_event_counts == expected_counts
