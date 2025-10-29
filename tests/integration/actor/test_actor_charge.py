from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest_asyncio

from apify_shared.consts import ActorJobStatus

from apify import Actor
from apify._models import ActorRun

if TYPE_CHECKING:
    from collections.abc import Iterable

    from apify_client import ApifyClientAsync
    from apify_client.clients import ActorClientAsync

    from .conftest import MakeActorFunction, RunActorFunction


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


def retry_counter(total_attempts: int) -> Iterable[tuple[bool, int]]:
    for retry in range(total_attempts - 1):
        yield False, retry

    yield True, total_attempts - 1


async def test_actor_charge_basic(
    ppe_actor: ActorClientAsync,
    run_actor: RunActorFunction,
    apify_client_async: ApifyClientAsync,
) -> None:
    run = await run_actor(ppe_actor)

    # Refetch until the platform gets its act together
    for is_last_attempt, _ in retry_counter(30):
        await asyncio.sleep(1)
        updated_run = await apify_client_async.run(run.id).get()
        run = ActorRun.model_validate(updated_run)

        try:
            assert run.status == ActorJobStatus.SUCCEEDED
            assert run.charged_event_counts == {'foobar': 4}
            break
        except AssertionError:
            if is_last_attempt:
                raise


async def test_actor_charge_limit(
    ppe_actor: ActorClientAsync,
    run_actor: RunActorFunction,
    apify_client_async: ApifyClientAsync,
) -> None:
    run = await run_actor(ppe_actor, max_total_charge_usd=Decimal('0.2'))

    # Refetch until the platform gets its act together
    for is_last_attempt, _ in retry_counter(30):
        await asyncio.sleep(1)
        updated_run = await apify_client_async.run(run.id).get()
        run = ActorRun.model_validate(updated_run)

        try:
            assert run.status == ActorJobStatus.SUCCEEDED
            assert run.charged_event_counts == {'foobar': 2}
            break
        except AssertionError:
            if is_last_attempt:
                raise
