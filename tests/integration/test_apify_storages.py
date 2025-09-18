import asyncio

import pytest

from crawlee import service_locator
from crawlee.storages import Dataset, KeyValueStore, RequestQueue

from apify import Configuration
from apify.storage_clients import ApifyStorageClient


@pytest.mark.parametrize(
    'storage_type',
    [Dataset, KeyValueStore, RequestQueue],
)
async def test_alias_concurrent_creation_local(
    storage_type: Dataset | KeyValueStore | RequestQueue, apify_token: str
) -> None:
    """Test that storages created with same alias are created only once even when created concurrently."""
    service_locator.set_configuration(Configuration(token=apify_token))
    service_locator.set_storage_client(ApifyStorageClient())
    tasks = [asyncio.create_task(storage_type.open(alias='test')) for _ in range(2)]

    storages = await asyncio.gather(*tasks)
    unique_storage_ids = {storage.id for storage in storages}
    try:
        # Only one aliased storage should be created.
        assert len(unique_storage_ids) == 1

        # Clean up
        await storages[0].drop()
    except AssertionError:
        for storage in storages:
            await storage.drop()
