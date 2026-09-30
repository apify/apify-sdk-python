import asyncio
from decimal import Decimal

from apify import Actor


async def main() -> None:
    async with Actor:
        # The budget this Actor run was started with, shared with its named child runs.
        budget = Actor.get_charging_manager().get_pricing_info().max_total_charge_usd
        Actor.log.info(f'Budget of this run: {budget} USD')

        # Give each of the three child runs a quarter of the budget, so they can all
        # start at once and this run keeps the rest for its own charges.
        per_child = Decimal(1) if budget.is_infinite() else budget / 4

        actor_runs = await asyncio.gather(
            *(
                Actor.call(
                    actor_id='apify/screenshot-url',
                    run_input={'urls': [{'url': f'https://www.apify.com/?page={page}'}]},
                    name=f'screenshot-{page}',
                    max_total_charge_usd=per_child,
                )
                for page in range(3)
            )
        )

        for actor_run in actor_runs:
            cost = actor_run.usage_total_usd
            Actor.log.info(f'Child run {actor_run.id} cost {cost} USD')


if __name__ == '__main__':
    asyncio.run(main())
