from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from ..._utils import poll_until_condition
from .conftest import get_scrapy_source_files

if TYPE_CHECKING:
    from apify_client import ApifyClientAsync

    from ..conftest import MakeActorFunction, RunActorFunction


async def test_ppe_spider_stops_pushing_once_over_budget(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
    apify_client_async: ApifyClientAsync,
) -> None:
    """A pay-per-event Scrapy Actor charges the synthetic dataset-item event and stops pushing once over budget."""
    actor = await make_actor(
        label='scrapy-ppe',
        source_files=get_scrapy_source_files('spider_basic.py', 'BasicSpider'),
        additional_requirements=['scrapy>=2.14.0'],
    )

    await actor.update(
        pricing_infos=[
            {
                'pricingModel': 'PAY_PER_EVENT',
                'apifyMarginPercentage': 0.0,
                'createdAt': '2024-01-01T00:00:00.000Z',
                'startedAt': '2024-01-01T00:00:00.000Z',
                'pricingPerEvent': {
                    'actorChargeEvents': {
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

    # The spider scrapes three products. At $0.05 an item, a $0.075 budget covers one of them. The second push
    # overcharges by one item, so the run is over budget and the third push is dropped and never charged.
    run = await run_actor(actor, max_total_charge_usd=Decimal('0.075'))

    # The overcharge makes the platform auto-abort the run, which races the Actor's clean exit.
    assert run.status in ('SUCCEEDED', 'ABORTED')

    expected_charges = {'apify-default-dataset-item': 2}

    # The SDK only tracks the synthetic event internally - the platform derives the charges from dataset writes
    # asynchronously, so they can lag behind the run reaching a terminal status. Refetch until they propagate.
    charged_run = await poll_until_condition(
        apify_client_async.run(run.id).get,
        lambda refetched: refetched is not None and refetched.charged_event_counts == expected_charges,
        timeout=120,
        poll_interval=1,
    )

    assert charged_run is not None
    assert charged_run.charged_event_counts == expected_charges

    # `total` counts the whole dataset, unlike `count`, which only covers the items returned in this page and
    # can still lag right after a run finishes.
    items = await actor.last_run().dataset().list_items()
    assert items.total == 2
