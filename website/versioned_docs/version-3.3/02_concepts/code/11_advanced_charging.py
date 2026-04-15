import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        charging_manager = Actor.get_charging_manager()

        # Check the total budget for this run
        max_charge = charging_manager.get_max_total_charge_usd()
        Actor.log.info(f'Max total charge: ${max_charge}')

        # Check how many events can still be charged
        remaining = charging_manager.calculate_max_event_charge_count_within_limit(
            'result-scraped',
        )
        Actor.log.info(f'Remaining chargeable events: {remaining}')

        # Get the total amount charged so far
        total_charged = charging_manager.calculate_total_charged_amount()
        Actor.log.info(f'Total charged so far: ${total_charged}')

        # Check all event types and their remaining counts
        chargeable = charging_manager.compute_chargeable()
        Actor.log.info(f'Chargeable events: {chargeable}')

        # Check if a specific event type has reached its limit
        if charging_manager.is_event_charge_limit_reached('result-scraped'):
            Actor.log.info('Budget exhausted for result-scraped events')


if __name__ == '__main__':
    asyncio.run(main())
