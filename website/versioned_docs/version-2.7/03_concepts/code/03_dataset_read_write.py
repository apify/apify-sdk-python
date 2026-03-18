from apify import Actor


async def main() -> None:
    async with Actor:
        # Open a dataset and write some data in it
        dataset = await Actor.open_dataset(name='my-cool-dataset')
        await dataset.push_data([{'itemNo': i} for i in range(1000)])

        # Read back the first half of the data
        first_half = await dataset.get_data(limit=500)
        Actor.log.info(f'The first half of items = {first_half.items}')

        # Iterate over the second half
        second_half = [item async for item in dataset.iterate_items(offset=500)]
        Actor.log.info(f'The second half of items = {second_half}')
