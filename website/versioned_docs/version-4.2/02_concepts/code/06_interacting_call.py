import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        # Start the apify/screenshot-url Actor and wait for it to finish.
        actor_run = await Actor.call(
            actor_id='apify/screenshot-url',
            run_input={
                'urls': [{'url': 'https://www.apify.com/'}],
                'delay': 1000,
                'waitUntil': 'load',
            },
        )

        # Get the Actor output from the dataset.
        run_client = Actor.apify_client.run(actor_run.id)
        dataset_client = run_client.dataset()
        item_list = await dataset_client.list_items()
        Actor.log.info(f'Actor output: {item_list.items}')


if __name__ == '__main__':
    asyncio.run(main())
