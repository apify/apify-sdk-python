import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        # Start the apify/screenshot-url Actor.
        actor_run = await Actor.call(
            actor_id='apify/screenshot-url',
            run_input={
                'urls': [{'url': 'https://www.apify.com/'}],
                'delay': 1000,
                'waitUntil': 'load',
            },
        )

        if actor_run is None:
            raise RuntimeError('Actor task failed to start.')

        # Wait for the Actor run to finish.
        run_client = Actor.apify_client.run(actor_run.id)
        await run_client.wait_for_finish()

        # Get the Actor output from the dataset.
        dataset_client = run_client.dataset()
        item_list = await dataset_client.list_items()
        Actor.log.info(f'Actor output: {item_list.items}')


if __name__ == '__main__':
    asyncio.run(main())
