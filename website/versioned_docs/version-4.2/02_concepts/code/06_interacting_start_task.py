import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        # Start the Actor task by its ID without waiting for it to finish.
        actor_run = await Actor.start_task(task_id='Z3m6FPSj0GYZ25rQc')

        # Log the run ID, which you can use to check on the run later.
        Actor.log.info(f'Started task run: {actor_run.id}')


if __name__ == '__main__':
    asyncio.run(main())
