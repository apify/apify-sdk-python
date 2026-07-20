import asyncio

from apify import Actor


async def main() -> None:
    async with Actor:
        # Open a named key-value store
        store = await Actor.open_key_value_store(name='my-cool-key-value-store')

        # Get the public URL of a record
        my_record_url = await store.get_public_url('my_record')
        Actor.log.info(f'URL of "my_record": {my_record_url}')


if __name__ == '__main__':
    asyncio.run(main())
