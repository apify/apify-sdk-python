import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        # Start the Actor task by its ID and wait for it to finish.
        actor_run = await Actor.call_task(task_id='Z3m6FPSj0GYZ25rQc')

        # Get the task run dataset items.
        run_client = Actor.apify_client.run(actor_run.id)
        dataset_client = run_client.dataset()
        items = await dataset_client.list_items()
        Actor.log.info(f'Task run dataset items: {items}')


if __name__ == '__main__':
    asyncio.run(main())
