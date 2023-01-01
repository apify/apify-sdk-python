from typing import AsyncIterator

import pytest_asyncio

from apify.memory_storage.memory_storage import MemoryStorage


@pytest_asyncio.fixture()
async def memory_storage(tmp_path: str) -> AsyncIterator[MemoryStorage]:
    ms = MemoryStorage(local_data_directory=tmp_path, write_metadata=True)
    yield ms
    await ms.purge()
