import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        for region in ['eu', 'us']:
            await Actor.start(
                actor_id='apify/screenshot-url',
                run_input={'urls': [{'url': f'https://www.apify.com/?region={region}'}]},
                run_name=f'screenshot-{region}',
            )

        # Wait for every named child run, including those started before a migration.
        for name, run_client in Actor.child_runs.items():
            run = await run_client.wait_for_finish()
            status = run.status if run else 'MISSING'
            Actor.log.info(f'Child run {name} finished as {status}')


if __name__ == '__main__':
    asyncio.run(main())
