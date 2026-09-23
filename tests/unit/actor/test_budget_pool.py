from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, Mock

import pytest

from apify_client._models import Run

from apify import Actor, BudgetExhaustedError, BudgetPool, Configuration
from apify._budget_pool import DEFAULT_BUDGET_POOL_KEY, get_run_charged_usd

if TYPE_CHECKING:
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


def make_client(runs: dict[str, Run]) -> Mock:
    client = Mock()

    def run(run_id: str) -> Mock:
        run_client = Mock()
        run_client.get = AsyncMock(return_value=runs.get(run_id))
        return run_client

    client.run = Mock(side_effect=run)
    return client


async def test_reservations_never_exceed_limit() -> None:
    async with Actor:
        pool = await BudgetPool.open(await Actor.open_key_value_store(), limit_usd=Decimal(10))

        first = await pool.reserve(Decimal(4))
        second = await pool.reserve(Decimal(4))
        third = await pool.reserve(Decimal(4))

        assert (first.amount_usd, second.amount_usd, third.amount_usd) == (Decimal(4), Decimal(4), Decimal(2))
        assert await pool.get_remaining_usd() == 0

        with pytest.raises(BudgetExhaustedError):
            await pool.reserve()


async def test_concurrent_reservations_split_the_budget() -> None:
    async with Actor:
        pool = await BudgetPool.open(
            await Actor.open_key_value_store(),
            limit_usd=Decimal(10),
            default_child_budget_usd=Decimal(3),
        )

        results = await asyncio.gather(*(pool.reserve() for _ in range(5)), return_exceptions=True)

        granted = [result.amount_usd for result in results if not isinstance(result, BaseException)]
        assert sorted(granted) == [Decimal(1), Decimal(3), Decimal(3), Decimal(3)]
        assert sum(isinstance(result, BudgetExhaustedError) for result in results) == 1


async def test_finished_child_returns_unused_budget() -> None:
    async with Actor:
        pool = await BudgetPool.open(await Actor.open_key_value_store(), limit_usd=Decimal(10))

        reservation = await pool.reserve(Decimal(6))
        await pool.track_run(reservation.id, make_run('child'))
        assert await pool.get_remaining_usd() == Decimal(4)

        finished = make_run('child', status='SUCCEEDED', charged_event_counts={'e': 3}, event_prices={'e': 0.5})
        await pool.update_run(finished)
        assert await pool.get_remaining_usd() == Decimal('8.5')

        entries = await pool.get_entries()
        assert entries[reservation.id].run_id == 'child'
        assert entries[reservation.id].charged_usd == Decimal('1.5')
        assert entries[reservation.id].is_finished


async def test_refresh_reads_child_charges_from_api() -> None:
    finished = make_run('child', status='SUCCEEDED', charged_event_counts={'e': 2}, event_prices={'e': 1})
    client = make_client({'child': finished})

    async with Actor:
        pool = await BudgetPool.open(await Actor.open_key_value_store(), limit_usd=Decimal(10), client=client)

        reservation = await pool.reserve(Decimal(10))
        await pool.track_run(reservation.id, make_run('child'))

        # The child finished in the meantime, so the next reservation sees the budget it did not use.
        next_reservation = await pool.reserve()
        assert next_reservation.amount_usd == Decimal(8)


async def test_state_is_persisted_in_key_value_store() -> None:
    async with Actor:
        kvs = await Actor.open_key_value_store()
        pool = await BudgetPool.open(kvs, limit_usd=Decimal(5))
        reservation = await pool.reserve(Decimal(2))
        await pool.record_charges('parent', Decimal(1))

        reopened = await BudgetPool.open(kvs)
        assert reopened.limit_usd == Decimal(5)
        assert set(await reopened.get_entries()) == {reservation.id, 'parent'}
        assert await reopened.get_remaining_usd() == Decimal(2)
        assert await reopened.get_charged_usd() == Decimal(1)

        stored = await kvs.get_value(DEFAULT_BUDGET_POOL_KEY)
        assert stored['limitUsd'] == '5'


async def test_record_charges_updates_existing_child_entry() -> None:
    async with Actor:
        pool = await BudgetPool.open(await Actor.open_key_value_store(), limit_usd=Decimal(10))
        reservation = await pool.reserve(Decimal(4))
        await pool.track_run(reservation.id, make_run('child'))

        # The child shares the pool and records its own charges - they must not be counted twice.
        await pool.record_charges('child', Decimal(3))

        assert set(await pool.get_entries()) == {reservation.id}
        assert await pool.get_remaining_usd() == Decimal(6)


async def test_release_drops_reservation() -> None:
    async with Actor:
        pool = await BudgetPool.open(await Actor.open_key_value_store(), limit_usd=Decimal(10))
        reservation = await pool.reserve(Decimal(4))
        await pool.release(reservation.id)
        assert await pool.get_remaining_usd() == Decimal(10)


async def test_unlimited_pool_only_tracks() -> None:
    async with Actor:
        pool = await BudgetPool.open(await Actor.open_key_value_store())
        assert (await pool.reserve()).amount_usd == Decimal('inf')
        assert (await pool.reserve(Decimal(3))).amount_usd == Decimal(3)


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


async def test_start_distributes_parent_budget(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    apify_client_async_patcher.patch('actor', 'start', return_value=make_run('child'))
    configuration = Configuration(max_total_charge_usd=Decimal(10), test_pay_per_event=True)

    async with Actor(configuration):
        await Actor.charge('event', count=2)  # Unknown events cost 1 USD each locally.

        await Actor.start('child-actor', max_total_charge_usd=Decimal(3))
        await Actor.start('child-actor', max_total_charge_usd=Decimal(100))

        with pytest.raises(BudgetExhaustedError):
            await Actor.start('child-actor')

        pool = await Actor.open_budget_pool()
        assert await pool.get_remaining_usd(refresh=False) == 0
        assert len(await pool.get_entries()) == 3  # The parent and two children.

    calls = apify_client_async_patcher.calls['actor']['start']
    # 10 USD limit minus the parent's own 2 USD: the first child asks for 3, the second is capped at the other 5.
    assert [kwargs['max_total_charge_usd'] for _, kwargs in calls] == [Decimal(3), Decimal(5)]


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


async def test_enforce_aborts_child_over_its_reservation() -> None:
    # A child not bound by `max_total_charge_usd` (e.g. pay-per-usage) that costs more than was reserved for it.
    over_budget = make_run('greedy', usage_total_usd=3)
    within_budget = make_run('modest', usage_total_usd=1)
    client = make_client({'greedy': over_budget, 'modest': within_budget})
    aborted_run = make_run('greedy', status='ABORTED', usage_total_usd=3)
    abort = AsyncMock(return_value=aborted_run)
    run_client_factory = client.run.side_effect

    def run(run_id: str) -> Mock:
        run_client = run_client_factory(run_id)
        run_client.abort = abort
        return run_client

    client.run.side_effect = run

    async with Actor:
        pool = await BudgetPool.open(await Actor.open_key_value_store(), limit_usd=Decimal(10), client=client)
        for run_id in ('greedy', 'modest'):
            reservation = await pool.reserve(Decimal(2))
            await pool.track_run(reservation.id, make_run(run_id))

        assert await pool.enforce() == ['greedy']
        abort.assert_awaited_once()

        entries = {entry.run_id: entry for entry in (await pool.get_entries()).values()}
        assert entries['greedy'].is_aborted_by_pool
        assert entries['greedy'].is_finished
        assert not entries['modest'].is_aborted_by_pool
        assert await pool.get_remaining_usd(refresh=False) == Decimal(5)


async def test_watcher_enforces_in_background() -> None:
    client = make_client({'greedy': make_run('greedy', usage_total_usd=3)})
    abort = AsyncMock(return_value=make_run('greedy', status='ABORTED', usage_total_usd=3))
    run_client_factory = client.run.side_effect

    def run(run_id: str) -> Mock:
        run_client = run_client_factory(run_id)
        run_client.abort = abort
        return run_client

    client.run.side_effect = run

    async with Actor:
        pool = await BudgetPool.open(
            await Actor.open_key_value_store(),
            limit_usd=Decimal(10),
            client=client,
            watch_interval=timedelta(milliseconds=10),
        )
        reservation = await pool.reserve(Decimal(2))
        await pool.track_run(reservation.id, make_run('greedy'))

        pool.start_watching()
        for _ in range(100):
            if abort.await_count:
                break
            await asyncio.sleep(0.01)
        await pool.stop_watching()

        abort.assert_awaited_once()


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


async def test_failed_start_releases_reservation(apify_client_async_patcher: ApifyClientAsyncPatcher) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError('start failed')

    apify_client_async_patcher.patch('actor', 'start', replacement_method=fail)
    configuration = Configuration(max_total_charge_usd=Decimal(10), test_pay_per_event=True)

    async with Actor(configuration):
        with pytest.raises(RuntimeError, match='start failed'):
            await Actor.start('child-actor', budget_pool='default')

        pool = await Actor.open_budget_pool()
        assert await pool.get_remaining_usd() == Decimal(10)
