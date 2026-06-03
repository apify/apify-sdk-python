import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        # Open a dataset with an alias — this creates an unnamed dataset
        # that can be referenced by this alias within the current run
        dataset = await Actor.open_dataset(alias='intermediate-results')
        await dataset.push_data({'step': 1, 'result': 'partial data'})

        # Later, open the same dataset using the same alias
        same_dataset = await Actor.open_dataset(alias='intermediate-results')
        data = await same_dataset.get_data()
        Actor.log.info(f'Items in dataset: {data.count}')


if __name__ == '__main__':
    asyncio.run(main())
