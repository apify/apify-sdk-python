from datetime import datetime, timezone
from unittest import mock
from unittest.mock import AsyncMock

import pytest

from crawlee.storage_clients import FileSystemStorageClient
from crawlee.storage_clients._file_system import FileSystemKeyValueStoreClient
from crawlee.storage_clients.models import StorageMetadata
from crawlee.storages._base import Storage

from apify import Actor, Configuration
from apify.storage_clients import ApifyStorageClient
from apify.storage_clients._apify import ApifyDatasetClient, ApifyKeyValueStoreClient, ApifyRequestQueueClient
from apify.storage_clients._file_system import ApifyFileSystemKeyValueStoreClient, ApifyFileSystemStorageClient
from apify.storages import Dataset, KeyValueStore, RequestQueue


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
    """Test that Storages based on `ApifyStorageClient` include `token` and `api_public_base_url` in
    additional cache key."""

    def create_metadata(id: str) -> StorageMetadata:
        now = datetime.now(tz=timezone.utc)
        return StorageMetadata(id=id, name=None, accessed_at=now, created_at=now, modified_at=now)

    storage_ids = iter(['1', '2', '3', '1', '3'])

    apify_storage_client = ApifyStorageClient()

    config_1 = Configuration(token='a')
    config_2 = Configuration(token='b')
    config_3 = Configuration(token='a', api_public_base_url='https://super_custom_api.com')

    config_4 = Configuration(token='a')
    config_5 = Configuration(token='a', api_public_base_url='https://super_custom_api.com')

    mocked_client = AsyncMock(spec=type[_storage_client])
    mocked_client.get_metadata = AsyncMock(side_effect=lambda: create_metadata(next(storage_ids)))
    mocked_open = AsyncMock(spec=_storage_client.open, return_value=mocked_client)

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


async def test_no_double_purge_for_filesystem_storage_client() -> None:
    expected_value = 'some value'
    expected_key = 'some key'

    async with Actor():
        await Actor.set_value(expected_key, expected_value)
        # RQ uses KVS under the hood for persistence, so it will try to open same default KVS as it was already opened,
        # but based on different client - FileSystemStorageClient.
        await Actor.open_request_queue()
        assert expected_value == await Actor.get_value(expected_key)


async def test_first_filesystem_storage_client_wins() -> None:
    """Test that when two different FileSystemStorageClient variants are used to open the same storage, they both use
    the same client that was used to open the storage first"""
    kvs_1 = await KeyValueStore.open(storage_client=ApifyFileSystemStorageClient())
    kvs_2 = await KeyValueStore.open(storage_client=FileSystemStorageClient())

    kvs_3 = await KeyValueStore.open(name='a', storage_client=FileSystemStorageClient())
    kvs_4 = await KeyValueStore.open(name='a', storage_client=ApifyFileSystemStorageClient())

    assert kvs_1 is kvs_2
    assert type(kvs_2._client) is ApifyFileSystemKeyValueStoreClient

    assert kvs_3 is kvs_4
    assert type(kvs_4._client) is FileSystemKeyValueStoreClient
