from apify import Actor


async def main() -> None:
    async with Actor:
        # Open a dataset and write some data in it
        dataset = await Actor.open_dataset(name='my-cool-dataset')
        await dataset.push_data([{'itemNo': i} for i in range(1000)])

        # Export the data as CSV
        await dataset.export_to(
            content_type='csv',
            key='data.csv',
            to_key_value_store_name='my-cool-key-value-store',
        )

        # Export the data as JSON
        await dataset.export_to(
            content_type='json',
            key='data.json',
            to_key_value_store_name='my-cool-key-value-store',
        )

        # Print the exported records
        store = await Actor.open_key_value_store(name='my-cool-key-value-store')

        csv_data = await store.get_value('data.csv')
        Actor.log.info(f'CSV data: {csv_data}')

        json_data = await store.get_value('data.json')
        Actor.log.info(f'JSON data: {json_data}')
