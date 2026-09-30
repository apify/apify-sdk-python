import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        # Keep at most 3 named child runs active at once.
        Actor.set_child_run_limits(max_concurrent_runs=3)

        urls = [f'https://www.apify.com/?page={page}' for page in range(6)]

        # Each call waits for a free slot before it starts its child run.
        actor_runs = await asyncio.gather(
            *(
                Actor.call(
                    actor_id='apify/screenshot-url',
                    run_input={'urls': [{'url': url}]},
                    name=f'screenshot-{index}',
                )
                for index, url in enumerate(urls)
            )
        )

        for actor_run in actor_runs:
            Actor.log.info(f'Child run {actor_run.id} finished as {actor_run.status}')


if __name__ == '__main__':
    asyncio.run(main())
