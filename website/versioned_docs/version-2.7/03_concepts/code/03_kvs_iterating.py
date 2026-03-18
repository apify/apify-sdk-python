from apify import Actor


async def main() -> None:
    async with Actor:
        # Open a named key-value store
        kvs = await Actor.open_key_value_store(name='my-cool-key-value-store')

        # Write some data to it
        await kvs.set_value('automatic_text', 'abcd')
        await kvs.set_value('automatic_json', {'ab': 'cd'})
        await kvs.set_value('explicit_csv', 'a,b\nc,d', content_type='text/csv')

        # Print the info for each record
        Actor.log.info('Records in store:')

        async for key, info in kvs.iterate_keys():
            Actor.log.info(f'key={key}, info={info}')
