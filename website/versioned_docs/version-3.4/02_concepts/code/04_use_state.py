import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        # Get or create an auto-persisted state dict.
        # On restart or migration, the state is loaded from the KVS.
        state = await Actor.use_state(default_value={'processed_items': 0})

        # Resume from previous state
        start_index = state['processed_items']
        Actor.log.info(f'Resuming from item {start_index}')

        # Do some work and update the state — it is persisted automatically
        for i in range(start_index, 100):  # ty: ignore[invalid-argument-type]
            Actor.log.info(f'Processing item {i}...')
            state['processed_items'] = i + 1
            await asyncio.sleep(0.1)


if __name__ == '__main__':
    asyncio.run(main())
