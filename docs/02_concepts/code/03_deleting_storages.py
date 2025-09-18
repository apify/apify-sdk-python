from apify import Actor


async def main() -> None:
    async with Actor:
        # Open a key-value store with the name 'my-cool-store'
        key_value_store = await Actor.open_key_value_store(name='my-cool-store')
        await key_value_store.set_value('record', 'Hello, world!')

        # Do something ...

        # Now we don't want it anymore
        await key_value_store.drop()
