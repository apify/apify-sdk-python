import asyncio

from apify import Actor, Request


async def main() -> None:
    async with Actor:
        # Work with the default dataset of the Actor
        dataset = await Actor.open_dataset()
        await dataset.push_data({'result': 'Hello, world!'})

        # Work with the key-value store with ID 'mIJVZsRQrDQf4rUAf'
        key_value_store = await Actor.open_key_value_store(id='mIJVZsRQrDQf4rUAf')
        await key_value_store.set_value('record', 'Hello, world!')

        # Work with the request queue with the name 'my-queue'
        request_queue = await Actor.open_request_queue(name='my-queue')
        await request_queue.add_request(Request.from_url('https://apify.com'))


if __name__ == '__main__':
    asyncio.run(main())
