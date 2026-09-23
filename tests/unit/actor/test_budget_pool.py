from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import Mock

import pytest

from apify_client._models import Run

from apify import (
    BUDGET_POOL_POLL_INTERVAL,
    Actor,
    BudgetExhaustedError,
    BudgetPool,
    BudgetPoolNestingError,
    Configuration,
)
from apify._budget_pool import DEFAULT_BUDGET_POOL_ALIAS, BudgetTracker, get_run_charged_usd

if TYPE_CHECKING:
    from ..conftest import ApifyClientAsyncPatcher
    from apify.storages import KeyValueStore


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


class Orchestrator:
    """One orchestrating run using a budget pool - its pool instance, tracker and own charges."""

    def __init__(self, run_id: str, client: FakeClient | None = None, *, poll_in_background: bool = False) -> None:
        self.run_id = run_id
        self.client = client or FakeClient()
        self.own_charged_usd = Decimal(0)
        # Tests that poll by hand keep the background watcher out of the way.
        poll_interval = timedelta(milliseconds=10) if poll_in_background else timedelta(hours=1)
        self.tracker = BudgetTracker(
            cast('Any', self.client), lambda: self.own_charged_usd, poll_interval=poll_interval
        )
        self.pool: BudgetPool

    async def open(self, key_value_store: KeyValueStore, limit_usd: Decimal | None = None) -> BudgetPool:
        self.pool = await BudgetPool.open(key_value_store, owner_run_id=self.run_id, limit_usd=limit_usd)
        await self.tracker.add_pool(self.pool)
        return self.pool

    async def start_child(self, run_id: str, amount_usd: Decimal | None = None) -> Decimal | None:
        max_charge_usd = await self.tracker.allocate([self.pool], amount_usd)
        self.client.runs[run_id] = make_run(run_id)
        await self.tracker.track([self.pool], self.client.runs[run_id], max_charge_usd)
        return max_charge_usd

    def set_child_charges(self, run_id: str, charged_usd: float, status: str = 'RUNNING') -> None:
        self.client.runs[run_id] = make_run(run_id, status=status, usage_total_usd=charged_usd)


def test_default_poll_interval() -> None:
    assert timedelta(seconds=5) == BUDGET_POOL_POLL_INTERVAL


async def test_orchestrator_writes_only_its_own_record() -> None:
    async with Actor:
        kvs = await Actor.open_key_value_store(alias='pool')
        orchestrator = Orchestrator('R')
        orchestrator.own_charged_usd = Decimal('0.4')
        await orchestrator.open(kvs, limit_usd=Decimal(10))

        assert await orchestrator.start_child('O', Decimal(6)) == Decimal(6)
        orchestrator.set_child_charges('O', 2.1)
        await orchestrator.tracker.poll()

        assert sorted([record.key async for record in kvs.iterate_keys()]) == ['LIMIT', 'RUN-R']
        assert await kvs.get_value('LIMIT') == {'limitUsd': '10'}
        record = await kvs.get_value('RUN-R')
        assert record['runId'] == 'R'
        assert record['status'] == 'RUNNING'
        assert record['ownChargedUsd'] == '0.4'
        assert record['children']['O']['maxChargeUsd'] == '6'
        assert record['children']['O']['chargedUsd'] == '2.1'
        assert record['children']['O']['status'] == 'RUNNING'

        assert orchestrator.pool.get_charged_usd() == Decimal('2.5')
        assert orchestrator.pool.get_remaining_usd() == Decimal('7.5')


async def test_charges_are_recorded_while_child_runs() -> None:
    async with Actor:
        orchestrator = Orchestrator('R')
        await orchestrator.open(await Actor.open_key_value_store(alias='pool'), limit_usd=Decimal(10))
        await orchestrator.start_child('child')

        orchestrator.set_child_charges('child', 2)
        await orchestrator.tracker.poll()
        assert orchestrator.pool.get_remaining_usd() == Decimal(8)

        orchestrator.set_child_charges('child', 6, status='SUCCEEDED')
        await orchestrator.tracker.poll()
        assert orchestrator.pool.get_remaining_usd() == Decimal(4)
        assert orchestrator.pool.get_records()['R'].children['child'].status == 'FINISHED'


async def test_allocation_is_capped_at_remaining_budget() -> None:
    async with Actor:
        orchestrator = Orchestrator('R')
        await orchestrator.open(await Actor.open_key_value_store(alias='pool'), limit_usd=Decimal(10))
        await orchestrator.start_child('first', Decimal(4))

        orchestrator.set_child_charges('first', 7)
        assert await orchestrator.start_child('second', Decimal(4)) == Decimal(3)

        orchestrator.set_child_charges('first', 10, status='SUCCEEDED')
        with pytest.raises(BudgetExhaustedError):
            await orchestrator.tracker.allocate([orchestrator.pool], None)


async def test_pool_exceeded_aborts_all_running_children() -> None:
    async with Actor:
        orchestrator = Orchestrator('R')
        await orchestrator.open(await Actor.open_key_value_store(alias='pool'), limit_usd=Decimal(10))
        await orchestrator.start_child('a')
        await orchestrator.start_child('b')

        orchestrator.set_child_charges('a', 5)
        orchestrator.set_child_charges('b', 5)
        assert await orchestrator.tracker.poll() == []

        orchestrator.set_child_charges('b', 5.01)
        assert sorted(await orchestrator.tracker.poll()) == ['a', 'b']
        children = orchestrator.pool.get_records()['R'].children
        assert {child.status for child in children.values()} == {'ABORTED_BY_POOL'}


async def test_child_over_its_own_limit_is_aborted() -> None:
    # A child not bound by `max_total_charge_usd` (e.g. pay-per-usage) that costs more than it was allocated.
    async with Actor:
        orchestrator = Orchestrator('R')
        await orchestrator.open(await Actor.open_key_value_store(alias='pool'), limit_usd=Decimal(100))
        await orchestrator.start_child('modest', Decimal(2))
        await orchestrator.start_child('greedy', Decimal(2))

        orchestrator.set_child_charges('modest', 2)
        orchestrator.set_child_charges('greedy', 2.2)
        assert await orchestrator.tracker.poll() == ['greedy']


async def test_watcher_polls_in_background() -> None:
    async with Actor:
        orchestrator = Orchestrator('R', poll_in_background=True)
        await orchestrator.open(await Actor.open_key_value_store(alias='pool'), limit_usd=Decimal(10))
        await orchestrator.start_child('child')

        orchestrator.set_child_charges('child', 11)
        for _ in range(100):
            if orchestrator.client.aborted:
                break
            await asyncio.sleep(0.01)
        assert orchestrator.client.aborted == ['child']
        await orchestrator.tracker.close()


async def test_parallel_orchestrators_share_a_named_pool() -> None:
    async with Actor:
        kvs = await Actor.open_key_value_store(name='team-budget')
        first, second = Orchestrator('R'), Orchestrator('S')
        await first.open(kvs, limit_usd=Decimal(10))
        await second.open(kvs)
        assert second.pool.limit_usd == Decimal(10)

        await first.start_child('child-r')
        await second.start_child('child-s')
        first.set_child_charges('child-r', 3)
        second.set_child_charges('child-s', 4)
        await asyncio.gather(first.tracker.poll(), second.tracker.poll())
        await asyncio.gather(first.pool.refresh(), second.pool.refresh())

        # Each wrote only its own record, and both see each other's charges.
        assert sorted([record.key async for record in kvs.iterate_keys()]) == ['LIMIT', 'RUN-R', 'RUN-S']
        assert first.pool.get_charged_usd() == second.pool.get_charged_usd() == Decimal(7)

        # Each aborts only the children it started.
        second.set_child_charges('child-s', 8)
        assert await second.tracker.poll() == ['child-s']
        assert await first.tracker.poll() == ['child-r']


async def test_nested_orchestrator_cannot_use_parent_pool() -> None:
    async with Actor:
        kvs = await Actor.open_key_value_store(name='team-budget')
        parent = Orchestrator('R')
        await parent.open(kvs, limit_usd=Decimal(10))
        await parent.start_child('O')

        with pytest.raises(BudgetPoolNestingError):
            await BudgetPool.open(kvs, owner_run_id='O')


async def test_children_of_finished_orchestrator_count_at_their_limit() -> None:
    async with Actor:
        kvs = await Actor.open_key_value_store(name='team-budget')
        orchestrator = Orchestrator('R')
        await orchestrator.open(kvs, limit_usd=Decimal(10))
        await orchestrator.start_child('running', Decimal(4))
        await orchestrator.start_child('done', Decimal(3))
        orchestrator.set_child_charges('running', 1)
        orchestrator.set_child_charges('done', 2, status='SUCCEEDED')

        await orchestrator.tracker.close()

        reader = await BudgetPool.open(kvs, owner_run_id='reader')
        record = reader.get_records()['R']
        assert record.status == 'FINISHED'
        assert record.unwatched_children == ['running']
        # The unwatched child counts at its 4 USD limit, the finished one at the 2 USD it charged.
        assert reader.get_charged_usd() == Decimal(6)


async def test_resurrected_orchestrator_resumes_polling() -> None:
    async with Actor:
        kvs = await Actor.open_key_value_store(name='team-budget')
        orchestrator = Orchestrator('R')
        await orchestrator.open(kvs, limit_usd=Decimal(10))
        await orchestrator.start_child('child', Decimal(4))
        await orchestrator.tracker.close()

        resurrected = Orchestrator('R', orchestrator.client, poll_in_background=True)
        await resurrected.open(kvs)
        assert resurrected.pool.get_records()['R'].status == 'RUNNING'

        resurrected.set_child_charges('child', 5)
        for _ in range(100):
            if resurrected.client.aborted:
                break
            await asyncio.sleep(0.01)
        assert resurrected.client.aborted == ['child']
        await resurrected.tracker.close()


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


async def test_start_uses_own_limit(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('child'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('child'))
    configuration = Configuration(max_total_charge_usd=Decimal(10), test_pay_per_event=True)

    async with Actor(configuration):
        await Actor.charge('event', count=2)  # Unknown events cost 1 USD each locally.

        await Actor.start('child-actor', max_total_charge_usd=Decimal(3))
        await Actor.start('child-actor')

        await Actor.charge('event', count=8)
        with pytest.raises(BudgetExhaustedError):
            await Actor.start('child-actor')

        kvs = await Actor.open_key_value_store(alias=DEFAULT_BUDGET_POOL_ALIAS)
        assert (await kvs.get_value('RUN-local'))['ownChargedUsd'] == '10'

    calls = apify_client_async_patcher.calls['actor']['start']
    # 10 USD limit minus the parent's own 2 USD: the first child asks for 3, the second gets the remaining 8.
    assert [kwargs['max_total_charge_usd'] for _, kwargs in calls] == [Decimal(3), Decimal(8)]


async def test_named_pool_and_own_limit_both_apply(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('child'))
    apify_client_async_patcher.patch('run', 'get', return_value=make_run('child'))
    configuration = Configuration(max_total_charge_usd=Decimal(10), test_pay_per_event=True)

    async with Actor(configuration):
        team_pool = await Actor.open_budget_pool(name='team-budget', limit_usd=Decimal(4))
        await Actor.start('child-actor', budget_pool=team_pool)

        # The child is recorded in both pools.
        own_pool = await Actor.open_budget_pool()
        assert 'child' in own_pool.get_records()['local'].children
        assert 'child' in team_pool.get_records()['local'].children

    calls = apify_client_async_patcher.calls['actor']['start']
    assert calls[0][1]['max_total_charge_usd'] == Decimal(4)


async def test_call_with_explicit_pool(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    finished = make_run('child', status='SUCCEEDED', charged_event_counts={'e': 1}, event_prices={'e': 2})
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('child'))
    apify_client_async_patcher.patch('run', 'wait_for_finish', return_value=finished)

    async with Actor:
        pool = await Actor.open_budget_pool(name='team-budget', limit_usd=Decimal(5))
        await Actor.call('child-actor', max_total_charge_usd=Decimal(4), budget_pool=pool, logger=None)

        child = pool.get_records()['local'].children['child']
        assert child.status == 'FINISHED'
        assert child.charged_usd == Decimal(2)
        assert pool.get_remaining_usd() == Decimal(3)

    calls = apify_client_async_patcher.calls['actor']['start']
    assert calls[0][1]['max_total_charge_usd'] == Decimal(4)
    assert len(apify_client_async_patcher.calls['run']['wait_for_finish']) == 1


async def test_start_without_limit_uses_no_pool(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('child'))

    async with Actor:
        await Actor.start('child-actor')
        await Actor.start('child-actor', max_total_charge_usd=Decimal(7))
        kvs = await Actor.open_key_value_store(alias=DEFAULT_BUDGET_POOL_ALIAS)
        assert [record.key async for record in kvs.iterate_keys()] == []

    calls = apify_client_async_patcher.calls['actor']['start']
    assert [kwargs['max_total_charge_usd'] for _, kwargs in calls] == [None, Decimal(7)]


async def test_failed_start_records_no_child(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError('start failed')

    apify_client_async_patcher.patch('actor', 'start', replacement_method=fail)
    configuration = Configuration(max_total_charge_usd=Decimal(10), test_pay_per_event=True)

    async with Actor(configuration):
        with pytest.raises(RuntimeError, match='start failed'):
            await Actor.start('child-actor')

        pool = await Actor.open_budget_pool()
        assert pool.get_records()['local'].children == {}
