import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        # Start the apify/screenshot-url Actor.
        actor_run = await Actor.call(
            actor_id='apify/screenshot-url',
            run_input={'url': 'http://example.com', 'delay': 10000},
        )

        if actor_run is None:
            raise RuntimeError('Actor task failed to start.')

        # Wait for the Actor run to finish.
        run_client = Actor.apify_client.run(actor_run.id)
        await run_client.wait_for_finish()

        # Get the Actor output from the key-value store.
        kvs_client = run_client.key_value_store()
        output = await kvs_client.get_record('OUTPUT')
        Actor.log.info(f'Actor output: {output}')


if __name__ == '__main__':
    asyncio.run(main())
