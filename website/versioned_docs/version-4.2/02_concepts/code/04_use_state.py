import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        # Get or create an auto-persisted state dict.
        # On restart or migration, the state is loaded from the KVS.
        state = await Actor.use_state(default_value={'processed_items': 0})

        # Resume from the persisted state (stored as JSON, so narrow the type).
        start_index = state['processed_items']
        if not isinstance(start_index, int):
            start_index = 0
        Actor.log.info(f'Resuming from item {start_index}')

        # Do some work and update the state — it is persisted automatically
        for i in range(start_index, 100):
            Actor.log.info(f'Processing item {i}...')
            state['processed_items'] = i + 1
            await asyncio.sleep(0.1)


if __name__ == '__main__':
    asyncio.run(main())
