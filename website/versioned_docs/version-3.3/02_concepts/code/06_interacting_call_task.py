import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        # Start the Actor task by its ID.
        actor_run = await Actor.call_task(task_id='Z3m6FPSj0GYZ25rQc')

        if actor_run is None:
            raise RuntimeError('Actor task failed to start.')

        # Wait for the task run to finish.
        run_client = Actor.apify_client.run(actor_run.id)
        await run_client.wait_for_finish()

        # Get the task run dataset items
        dataset_client = run_client.dataset()
        items = await dataset_client.list_items()
        Actor.log.info(f'Task run dataset items: {items}')


if __name__ == '__main__':
    asyncio.run(main())
