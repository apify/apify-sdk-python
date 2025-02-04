from apify import Actor


async def main() -> None:
    async with Actor:
        # Open a named key-value store
        kvs = await Actor.open_key_value_store(name='my-cool-key-value-store')

        # Write some data to it
        await kvs.set_value('automatic_text', 'abcd')
        await kvs.set_value('automatic_json', {'ab': 'cd'})
        await kvs.set_value('explicit_csv', 'a,b\nc,d', content_type='text/csv')

        # Get the values and log them
        automatic_text = await kvs.get_value('automatic_text')
        Actor.log.info(f'Automatic text: {automatic_text}')

        automatic_json = await kvs.get_value('automatic_json')
        Actor.log.info(f'Automatic JSON: {automatic_json}')

        explicit_csv = await kvs.get_value('explicit_csv')
        Actor.log.info(f'Explicit CSV: {explicit_csv}')

        # Delete the `automatic_text` value
        await kvs.set_value('automatic_text', None)
