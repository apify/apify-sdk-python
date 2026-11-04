import asyncio

from crawlee import service_locator

from apify import Actor
from apify.storage_clients import ApifyStorageClient, SmartApifyStorageClient


async def main() -> None:
    # Use the shared Apify request queue client, which supports multiple
    # consumers working on the same queue at the cost of more API calls.
    cloud_storage_client = ApifyStorageClient(request_queue_access='shared')
    service_locator.set_storage_client(
        SmartApifyStorageClient(cloud_storage_client=cloud_storage_client),
    )

    async with Actor:
        request_queue = await Actor.open_request_queue()
        await request_queue.add_request('https://crawlee.dev')


if __name__ == '__main__':
    asyncio.run(main())
