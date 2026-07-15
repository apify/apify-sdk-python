from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from crawlee.configuration import Configuration
from crawlee.storage_clients import FileSystemStorageClient

from ._dataset_client import ApifyFileSystemDatasetClient
from ._key_value_store_client import ApifyFileSystemKeyValueStoreClient
from apify._utils import docs_group

if TYPE_CHECKING:
    from collections.abc import Hashable

    from crawlee.storage_clients._file_system import FileSystemKeyValueStoreClient


@docs_group('Storage clients')
class ApifyFileSystemStorageClient(FileSystemStorageClient):
    """Apify SDK variant of Crawlee's `FileSystemStorageClient`, used as the default local storage client.

    It extends the Crawlee file-system client with Apify-specific behavior that keeps local runs consistent
    with the Apify platform:

    - Key-value stores use `ApifyFileSystemKeyValueStoreClient`, which preserves the Actor input file (e.g.
      `INPUT.json`) and the metadata file when purging, and maps the logical `INPUT` key to the input file on
      disk.
    - Datasets use `ApifyFileSystemDatasetClient`, which charges for the `PAY_PER_EVENT` pricing model so it
      can be exercised locally.
    """

    @override
    def get_storage_client_cache_key(self, configuration: Configuration) -> Hashable:
        # Ensure same cache key as the `FileSystemStorageClient` to prevent potential purging of the path twice.
        # If `FileSystemStorageClient` opens the storage first, it will be used even in successive open calls by
        # `ApifyFileSystemStorageClient` and vice versa.
        return FileSystemStorageClient().get_storage_client_cache_key(configuration)

    @override
    async def create_kvs_client(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        alias: str | None = None,
        configuration: Configuration | None = None,
    ) -> FileSystemKeyValueStoreClient:
        configuration = configuration or Configuration.get_global_configuration()
        client = await ApifyFileSystemKeyValueStoreClient.open(
            id=id,
            name=name,
            alias=alias,
            configuration=configuration,
        )
        await self._purge_if_needed(client, configuration)
        return client

    @override
    async def create_dataset_client(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        alias: str | None = None,
        configuration: Configuration | None = None,
    ) -> ApifyFileSystemDatasetClient:
        configuration = configuration or Configuration.get_global_configuration()
        client = await ApifyFileSystemDatasetClient.open(
            id=id,
            name=name,
            alias=alias,
            configuration=configuration,
        )
        await self._purge_if_needed(client, configuration)
        return client
