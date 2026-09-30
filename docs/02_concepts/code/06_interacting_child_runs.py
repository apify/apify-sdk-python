import asyncio
from collections import Counter

from apify import Actor


async def main() -> None:
    async with Actor:
        for region in ['eu', 'us']:
            await Actor.start(
                actor_id='apify/screenshot-url',
                run_input={'urls': [{'url': f'https://www.apify.com/?region={region}'}]},
                name=f'screenshot-{region}',
            )

        # Count the child runs by their current status.
        child_runs = await Actor.child_runs()
        statuses = Counter(
            child_run.run.status if child_run.run else 'MISSING'
            for child_run in child_runs.values()
        )
        Actor.log.info(f'Child runs by status: {dict(statuses)}')

        # Report the names whose earlier runs failed and were replaced.
        for name, child_run in child_runs.items():
            if child_run.previous_run_ids:
                Actor.log.info(f'{name} failed {len(child_run.previous_run_ids)} time(s)')


if __name__ == '__main__':
    asyncio.run(main())
