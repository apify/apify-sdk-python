from __future__ import annotations

import json
import os
from decimal import Decimal
from functools import partial
from typing import TYPE_CHECKING

import impit
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


async def test_actor_charge_in_multi_tenant_standby_run(
    make_actor: MakeActorFunction,
    apify_client_async: ApifyClientAsync,
    apify_token: str,
) -> None:
    """Test that a multi-tenant Server Actor run charges with the request ID and rejects charges without it."""

    async def main() -> None:
        import json

        import uvicorn

        async def app(scope, receive, send):  # noqa: ANN001, ANN202, ARG001
            headers = dict(scope['headers'])
            if b'x-apify-container-server-readiness-probe' in headers:
                body = b'ready'
            else:
                request_id = headers.get(b'x-actor-request-id', b'').decode() or None
                if scope['query_string'] == b'omit_request_id':
                    request_id = None
                try:
                    result = await Actor.charge(event_name='api-call', request_id=request_id)
                    body = json.dumps({'charged_count': result.charged_count, 'request_id': request_id}).encode()
                except ValueError as exc:
                    body = json.dumps({'error': str(exc)}).encode()
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': body})

        async with Actor:
            config = uvicorn.Config(app, host='0.0.0.0', port=Actor.configuration.web_server_port)  # noqa: S104
            await uvicorn.Server(config).serve()

    actor_client = await make_actor('ppe-multi-tenant', main_func=main)
    await actor_client.update(
        pricing_infos=[
            {
                'pricingModel': 'PAY_PER_EVENT',
                'apifyMarginPercentage': 0.0,
                'createdAt': '2024-01-01T00:00:00.000Z',
                'startedAt': '2024-01-01T00:00:00.000Z',
                'pricingPerEvent': {
                    'actorChargeEvents': {
                        'api-call': {
                            'eventTitle': 'API call',
                            'eventPriceUsd': 0.01,
                            'eventDescription': 'One API call',
                        },
                    },
                },
            },
        ],
    )

    actor = await actor_client.get()
    assert actor is not None
    auth = {'Authorization': f'Bearer {apify_token}'}

    async with impit.AsyncClient(timeout=120) as http:
        # `ActorClientAsync.update()` has no tenancy argument, so the field is set through the API directly.
        api_url = os.getenv('APIFY_INTEGRATION_TESTS_API_URL', 'https://api.apify.com')
        response = await http.put(
            f'{api_url}/v2/acts/{actor.id}',
            headers={**auth, 'Content-Type': 'application/json'},
            content=json.dumps({'actorStandby': {'isEnabled': True, 'tenancy': 'MULTI_TENANT'}}),
        )
        assert response.status_code == 200, response.text

        actor = await actor_client.get()
        assert actor is not None
        assert actor.standby_url is not None

        try:
            with_id = (await http.get(actor.standby_url, headers=auth)).json()
            without_id = (await http.get(f'{actor.standby_url}?omit_request_id', headers=auth)).json()
        finally:
            runs = await actor_client.runs().list()
            for run_item in runs.items:
                await apify_client_async.run(run_item.id).abort()

    assert with_id['charged_count'] == 1
    assert with_id['request_id']
    assert 'request_id' in without_id['error']

    run = await _get_run(apify_client_async, runs.items[0].id)
    assert run.standby is not None
    assert run.standby.deployment.startswith('MULTI_TENANT')
