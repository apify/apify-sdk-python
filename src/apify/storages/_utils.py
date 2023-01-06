from typing import Union

from apify_client import ApifyClientAsync

from ..memory_storage.memory_storage import MemoryStorage


async def _purge_default_storages(client: Union[ApifyClientAsync, MemoryStorage]) -> None:
    if isinstance(client, MemoryStorage) and not client._purged:
        client._purged = True
        await client.purge()
