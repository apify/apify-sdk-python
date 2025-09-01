from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from crawlee.storage_clients._base import StorageClient

from ._dataset_client import ApifyDatasetClient
from ._key_value_store_client import ApifyKeyValueStoreClient
from ._request_queue_client import ApifyRequestQueueClient
from apify._configuration import service_locator
from apify._utils import docs_group

if TYPE_CHECKING:
    from crawlee.configuration import Configuration


@docs_group('Storage clients')
class ApifyStorageClient(StorageClient):
    """Apify storage client."""

    def __init__(self, configuration: Configuration | None = None) -> None:
        """Initialize the file system storage client.

        Args:
            configuration: Optional configuration instance to use with the storage client.
                If not provided, the global configuration will be used.
        """
        self._configuration = configuration or service_locator.get_configuration()

    @override
    async def create_dataset_client(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        configuration: Configuration | None = None,
    ) -> ApifyDatasetClient:
        # Import here to avoid circular imports.
        from apify import Configuration as ApifyConfiguration  # noqa: PLC0415

        if isinstance(self._configuration, ApifyConfiguration):
            return await ApifyDatasetClient.open(id=id, name=name, configuration=self._configuration)

        raise TypeError(
            f'Expected "configuration" to be an instance of "apify.Configuration", '
            f'but got {type(self._configuration).__name__} instead.'
        )

    @override
    async def create_kvs_client(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        configuration: Configuration | None = None,
    ) -> ApifyKeyValueStoreClient:
        # Import here to avoid circular imports.
        from apify import Configuration as ApifyConfiguration  # noqa: PLC0415

        if isinstance(self._configuration, ApifyConfiguration):
            return await ApifyKeyValueStoreClient.open(id=id, name=name, configuration=self._configuration)

        raise TypeError(
            f'Expected "configuration" to be an instance of "apify.Configuration", '
            f'but got {type(self._configuration).__name__} instead.'
        )

    @override
    async def create_rq_client(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        configuration: Configuration | None = None,
    ) -> ApifyRequestQueueClient:
        # Import here to avoid circular imports.
        from apify import Configuration as ApifyConfiguration  # noqa: PLC0415

        if isinstance(self._configuration, ApifyConfiguration):
            return await ApifyRequestQueueClient.open(id=id, name=name, configuration=self._configuration)

        raise TypeError(
            f'Expected "configuration" to be an instance of "apify.Configuration", '
            f'but got {type(self._configuration).__name__} instead.'
        )

    @override
    def create_client(self, configuration: Configuration) -> ApifyStorageClient:
        """Create a storage client from an existing storage client potentially just replacing the configuration."""
        return ApifyStorageClient(configuration)
