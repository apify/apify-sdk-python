import asyncio

from crawlee import service_locator

from apify import Actor
from apify.storage_clients import MemoryStorageClient, SmartApifyStorageClient


async def main() -> None:
    # Keep all local data in memory instead of writing it to the filesystem
    # when running outside the Apify platform.
    local_storage_client = MemoryStorageClient()
    service_locator.set_storage_client(
        SmartApifyStorageClient(local_storage_client=local_storage_client),
    )

    async with Actor:
        store = await Actor.open_key_value_store()
        await store.set_value('example', {'hello': 'world'})


if __name__ == '__main__':
    asyncio.run(main())
