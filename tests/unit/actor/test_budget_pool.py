from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import Mock

import pytest

from apify_client._models import Run

from apify import BUDGET_POOL_POLL_INTERVAL, Actor, BudgetExhaustedError, BudgetPool, Configuration
from apify._budget_pool import DEFAULT_BUDGET_POOL_KEY, get_run_charged_usd

if TYPE_CHECKING:
    from apify_client import ApifyClientAsync

    from ..conftest import ApifyClientAsyncPatcher


def make_run(
    run_id: str = 'run-1',
    *,
    status: str = 'RUNNING',
    charged_event_counts: dict[str, int] | None = None,
    event_prices: dict[str, float] | None = None,
    usage_total_usd: float | None = None,
) -> Run:
    data: dict[str, Any] = {
        'id': run_id,
        'buildId': 'build-id',
        'actId': 'actor-id',
        'userId': 'user-id',
        'startedAt': '2024-08-08T12:12:44Z',
        'status': status,
        'meta': {'origin': 'API'},
        'defaultDatasetId': 'dataset-id',
        'defaultKeyValueStoreId': 'kvs-id',
        'defaultRequestQueueId': 'rq-id',
        'stats': {'restartCount': 0, 'resurrectCount': 0, 'computeUnits': 0},
        'options': {'build': 'latest', 'timeoutSecs': 60, 'memoryMbytes': 1024, 'diskMbytes': 2048},
        'chargedEventCounts': charged_event_counts,
        'usageTotalUsd': usage_total_usd,
    }
    if event_prices is not None:
        data['pricingInfo'] = {
            'pricingModel': 'PAY_PER_EVENT',
            'apifyMarginPercentage': 0,
            'createdAt': '2024-08-08T12:12:44Z',
            'startedAt': '2024-08-08T12:12:44Z',
            'pricingPerEvent': {
                'actorChargeEvents': {
                    name: {'eventTitle': name, 'eventPriceUsd': price, 'eventDescription': name}
                    for name, price in event_prices.items()
                }
            },
        }
    return Run.model_validate(data)


class FakeClient:
    """Serves the latest state of runs by ID, and records aborts."""

    def __init__(self) -> None:
        self.runs: dict[str, Run] = {}
        self.aborted: list[str] = []

    def run(self, run_id: str) -> Mock:
        run_client = Mock()

        async def get() -> Run | None:
            return self.runs.get(run_id)

        async def abort(**_kwargs: Any) -> Run:
            self.aborted.append(run_id)
            aborted = self.runs[run_id].model_copy(update={'status': 'ABORTED'})
            self.runs[run_id] = aborted
            return aborted

        run_client.get = get
        run_client.abort = abort
        return run_client


async def open_pool(client: FakeClient | None = None, **kwargs: Any) -> BudgetPool:
    return await BudgetPool.open(
        await Actor.open_key_value_store(),
        client=cast('ApifyClientAsync | None', client),
        **kwargs,
    )


async def start_child(pool: BudgetPool, client: FakeClient, run_id: str, amount_usd: Decimal | None = None) -> str:
    allocation = await pool.allocate(amount_usd)
    client.runs[run_id] = make_run(run_id)
    await pool.track_run(allocation.id, client.runs[run_id])
    return allocation.id


def test_default_poll_interval() -> None:
    assert timedelta(seconds=5) == BUDGET_POOL_POLL_INTERVAL


async def test_charges_are_counted_while_child_runs() -> None:
    client = FakeClient()

    async with Actor:
        pool = await open_pool(client, limit_usd=Decimal(10))
        await start_child(pool, client, 'child')

        client.runs['child'] = make_run('child', usage_total_usd=2)
        assert await pool.get_remaining_usd() == Decimal(8)

        client.runs['child'] = make_run('child', usage_total_usd=5)
        assert await pool.get_remaining_usd() == Decimal(5)

        client.runs['child'] = make_run('child', status='SUCCEEDED', usage_total_usd=6)
        assert await pool.get_remaining_usd() == Decimal(4)
        entry = next(iter((await pool.get_entries()).values()))
        assert entry.is_finished
        assert entry.charged_usd == Decimal(6)


async def test_allocation_is_capped_at_live_remaining_budget() -> None:
    client = FakeClient()

    async with Actor:
        pool = await open_pool(client, limit_usd=Decimal(10))
        first = await start_child(pool, client, 'first', Decimal(4))

        client.runs['first'] = make_run('first', usage_total_usd=7)
        second = await pool.allocate(Decimal(4))
        assert second.amount_usd == Decimal(3)

        client.runs['first'] = make_run('first', usage_total_usd=10)
        with pytest.raises(BudgetExhaustedError):
            await pool.allocate()

        assert (await pool.get_entries())[first].max_charge_usd == Decimal(4)


async def test_enforce_aborts_all_children_when_pool_exceeded_beyond_tolerance() -> None:
    client = FakeClient()

    async with Actor:
        pool = await open_pool(client, limit_usd=Decimal(10), overshoot_tolerance=Decimal('0.05'))
        await start_child(pool, client, 'a')
        await start_child(pool, client, 'b')

        # 10.4 USD is within the 5 % tolerance of the 10 USD limit.
        client.runs['a'] = make_run('a', usage_total_usd=5)
        client.runs['b'] = make_run('b', usage_total_usd=5.4)
        assert await pool.enforce() == []

        client.runs['b'] = make_run('b', usage_total_usd=5.6)
        assert sorted(await pool.enforce()) == ['a', 'b']
        assert sorted(client.aborted) == ['a', 'b']

        entries = list((await pool.get_entries()).values())
        assert all(entry.is_aborted_by_pool and entry.is_finished for entry in entries)


async def test_enforce_aborts_child_over_its_own_limit() -> None:
    # A child not bound by `max_total_charge_usd` (e.g. pay-per-usage) that costs more than it was allocated.
    client = FakeClient()

    async with Actor:
        pool = await open_pool(client, limit_usd=Decimal(100), overshoot_tolerance=Decimal('0.05'))
        await start_child(pool, client, 'modest', Decimal(2))
        await start_child(pool, client, 'greedy', Decimal(2))

        client.runs['modest'] = make_run('modest', usage_total_usd=2.05)
        client.runs['greedy'] = make_run('greedy', usage_total_usd=2.2)

        assert await pool.enforce() == ['greedy']
        assert client.aborted == ['greedy']


async def test_watcher_polls_in_background() -> None:
    client = FakeClient()

    async with Actor:
        pool = await open_pool(client, limit_usd=Decimal(10), poll_interval=timedelta(milliseconds=10))
        await start_child(pool, client, 'child')
        pool.start_watching()

        client.runs['child'] = make_run('child', usage_total_usd=3)
        for _ in range(100):
            if (await pool.get_charged_usd()) == Decimal(3):
                break
            await asyncio.sleep(0.01)
        assert await pool.get_charged_usd() == Decimal(3)

        client.runs['child'] = make_run('child', usage_total_usd=11)
        for _ in range(100):
            if client.aborted:
                break
            await asyncio.sleep(0.01)
        await pool.stop_watching()

        assert client.aborted == ['child']


async def test_tracked_own_charges_are_recorded_on_every_poll() -> None:
    own_charges = Decimal(1)

    async with Actor:
        pool = await open_pool(limit_usd=Decimal(10))
        pool.track_charges('parent', lambda: own_charges)

        assert await pool.get_remaining_usd() == Decimal(9)
        own_charges = Decimal(4)
        assert await pool.get_remaining_usd() == Decimal(6)


async def test_state_is_persisted_in_key_value_store() -> None:
    async with Actor:
        kvs = await Actor.open_key_value_store()
        pool = await BudgetPool.open(kvs, limit_usd=Decimal(5))
        allocation = await pool.allocate(Decimal(2))
        await pool.record_charges('parent', Decimal(1))

        reopened = await BudgetPool.open(kvs)
        assert reopened.limit_usd == Decimal(5)
        assert set(await reopened.get_entries()) == {allocation.id, 'parent'}
        assert await reopened.get_remaining_usd() == Decimal(4)
        assert await reopened.get_charged_usd() == Decimal(1)

        stored = await kvs.get_value(DEFAULT_BUDGET_POOL_KEY)
        assert stored['limitUsd'] == '5'


async def test_record_charges_updates_existing_child_entry() -> None:
    client = FakeClient()

    async with Actor:
        pool = await open_pool(client, limit_usd=Decimal(10))
        allocation_id = await start_child(pool, client, 'child', Decimal(4))

        # The child shares the pool and records its own charges - they must not be counted twice.
        await pool.record_charges('child', Decimal(3))

        assert set(await pool.get_entries()) == {allocation_id}
        assert await pool.get_remaining_usd(refresh=False) == Decimal(7)


async def test_release_drops_allocation() -> None:
    async with Actor:
        pool = await open_pool(limit_usd=Decimal(10))
        allocation = await pool.allocate(Decimal(4))
        await pool.release(allocation.id)
        assert await pool.get_entries() == {}


async def test_unlimited_pool_only_tracks() -> None:
    async with Actor:
        pool = await open_pool()
        assert (await pool.allocate()).amount_usd == Decimal('inf')
        assert (await pool.allocate(Decimal(3))).amount_usd == Decimal(3)


def test_get_run_charged_usd() -> None:
    assert get_run_charged_usd(make_run(charged_event_counts={'a': 2, 'b': 1}, event_prices={'a': 0.1, 'b': 1})) == (
        Decimal('1.2')
    )
    # Unknown event price falls back to the total usage.
    assert get_run_charged_usd(
        make_run(charged_event_counts={'x': 2}, event_prices={'a': 0.1}, usage_total_usd=0.7)
    ) == Decimal('0.7')
    assert get_run_charged_usd(make_run(usage_total_usd=0.25)) == Decimal('0.25')
    assert get_run_charged_usd(make_run()) == Decimal(0)


async def test_start_uses_parent_budget(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('child'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('child'))
    configuration = Configuration(max_total_charge_usd=Decimal(10), test_pay_per_event=True)

    async with Actor(configuration):
        await Actor.charge('event', count=2)  # Unknown events cost 1 USD each locally.

        await Actor.start('child-actor', max_total_charge_usd=Decimal(3))
        await Actor.start('child-actor')

        # The parent's own charges are picked up live, without another child being started.
        await Actor.charge('event', count=8)
        pool = await Actor.open_budget_pool()
        assert await pool.get_remaining_usd() == 0

        with pytest.raises(BudgetExhaustedError):
            await Actor.start('child-actor')

    calls = apify_client_async_patcher.calls['actor']['start']
    # 10 USD limit minus the parent's own 2 USD: the first child asks for 3, the second gets the remaining 8.
    assert [kwargs['max_total_charge_usd'] for _, kwargs in calls] == [Decimal(3), Decimal(8)]


async def test_call_with_explicit_pool(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    finished = make_run('child', status='SUCCEEDED', charged_event_counts={'e': 1}, event_prices={'e': 2})
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('child'))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=finished)

    async with Actor:
        pool = await Actor.open_budget_pool(alias='shared-budget', limit_usd=Decimal(5))
        await Actor.call('child-actor', max_total_charge_usd=Decimal(4), budget_pool=pool, logger=None)

        assert await pool.get_remaining_usd(refresh=False) == Decimal(3)
        entry = next(iter((await pool.get_entries()).values()))
        assert entry.run_id == 'child'
        assert entry.is_finished

    calls = apify_client_async_patcher.calls['actor']['start']
    assert calls[0][1]['max_total_charge_usd'] == Decimal(4)
    assert len(apify_client_async_patcher.calls['run']['wait_for_finish']) == 1


async def test_start_without_limit_passes_max_charge_through(
    apify_client_async_patcher: ApifyClientAsyncPatcher,
) -> None:
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('child'))

    async with Actor:
        await Actor.start('child-actor')
        await Actor.start('child-actor', max_total_charge_usd=Decimal(7))
        assert await (await Actor.open_key_value_store()).get_value(DEFAULT_BUDGET_POOL_KEY) is None

    calls = apify_client_async_patcher.calls['actor']['start']
    assert [kwargs['max_total_charge_usd'] for _, kwargs in calls] == [None, Decimal(7)]


async def test_failed_start_releases_allocation(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError('start failed')

    apify_client_async_patcher.patch('actor', 'start', replacement_method=fail)
    configuration = Configuration(max_total_charge_usd=Decimal(10), test_pay_per_event=True)

    async with Actor(configuration):
        with pytest.raises(RuntimeError, match='start failed'):
            await Actor.start('child-actor', budget_pool='default')

        pool = await Actor.open_budget_pool()
        assert all(not entry.is_child_run for entry in (await pool.get_entries()).values())
