from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from crawlee.configuration import Configuration
from crawlee.storage_clients import FileSystemStorageClient

from ._key_value_store_client import ApifyFileSystemKeyValueStoreClient

if TYPE_CHECKING:
    from crawlee.storage_clients._file_system import FileSystemKeyValueStoreClient


class ApifyFileSystemStorageClient(FileSystemStorageClient):
    """Apify-specific implementation of the file system storage client.

    The only difference is that it uses `ApifyFileSystemKeyValueStoreClient` for key-value stores,
    which overrides the `purge` method to delete all files in the key-value store directory
    except for the metadata file and the `INPUT.json` file.
    """

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
