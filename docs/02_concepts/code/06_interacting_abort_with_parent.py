import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        # Start the child run, and abort it if this Actor run is gracefully aborted.
        actor_run = await Actor.start(
            actor_id='apify/screenshot-url',
            run_input={'urls': [{'url': 'https://www.apify.com/'}]},
            name='screenshot',
            abort_with_parent=True,
        )

        Actor.log.info(f'Started child run {actor_run.id}')


if __name__ == '__main__':
    asyncio.run(main())
