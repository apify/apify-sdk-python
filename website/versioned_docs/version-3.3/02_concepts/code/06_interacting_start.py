import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        # Start your own Actor named 'my-fancy-actor'.
        actor_run = await Actor.start(
            actor_id='~my-fancy-actor',
            run_input={'foo': 'bar'},
        )

        # Log the Actor run ID.
        Actor.log.info(f'Actor run ID: {actor_run.id}')


if __name__ == '__main__':
    asyncio.run(main())
