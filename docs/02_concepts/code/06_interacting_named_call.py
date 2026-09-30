import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        # Call the apify/screenshot-url Actor under the name 'screenshot'. If this run
        # migrates while the child is running, the same call after the restart waits
        # for the recorded child run instead of starting a new one.
        actor_run = await Actor.call(
            actor_id='apify/screenshot-url',
            run_input={'urls': [{'url': 'https://www.apify.com/'}]},
            name='screenshot',
        )

        Actor.log.info(f'Child run {actor_run.id} finished with {actor_run.status}')


if __name__ == '__main__':
    asyncio.run(main())
