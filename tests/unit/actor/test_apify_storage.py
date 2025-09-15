from unittest import mock
from unittest.mock import AsyncMock

import pytest

from crawlee.storages import Dataset, KeyValueStore, RequestQueue
from crawlee.storages._base import Storage

from apify import Configuration
from apify.storage_clients import ApifyStorageClient
from apify.storage_clients._apify import ApifyDatasetClient, ApifyKeyValueStoreClient, ApifyRequestQueueClient


@pytest.mark.parametrize(
    ('storage', '_storage_client'),
    [
        (Dataset, ApifyDatasetClient),
        (KeyValueStore, ApifyKeyValueStoreClient),
        (RequestQueue, ApifyRequestQueueClient),
    ],
)
async def test_get_additional_cache_key(
    storage: Storage, _storage_client: ApifyDatasetClient | ApifyKeyValueStoreClient | ApifyRequestQueueClient
) -> None:
    """Test that Storages based on `ApifyStorageClient` include `token` and `api_base_url` in additional cache key."""
    storage_names = iter(['1', '2', '3', '1', '3'])

    apify_storage_client = ApifyStorageClient()

    config_1 = Configuration(token='a')
    config_2 = Configuration(token='b')
    config_3 = Configuration(token='a', api_base_url='https://super_custom_api.com')

    config_4 = Configuration(token='a')
    config_5 = Configuration(token='a', api_base_url='https://super_custom_api.com')

    mocked_open = AsyncMock(spec=_storage_client.open)
    mocked_open.get_metadata = AsyncMock(storage_names)

    with mock.patch.object(_storage_client, 'open', mocked_open):
        storage_1 = await storage.open(storage_client=apify_storage_client, configuration=config_1)
        storage_2 = await storage.open(storage_client=apify_storage_client, configuration=config_2)
        storage_3 = await storage.open(storage_client=apify_storage_client, configuration=config_3)
        storage_4 = await storage.open(storage_client=apify_storage_client, configuration=config_4)
        storage_5 = await storage.open(storage_client=apify_storage_client, configuration=config_5)

        # Different configuration results in different storage clients.
        assert storage_1 is not storage_2
        assert storage_1 is not storage_3
        assert storage_2 is not storage_3

        # Equivalent configuration results in same storage clients.
        assert storage_1 is storage_4
        assert storage_3 is storage_5
