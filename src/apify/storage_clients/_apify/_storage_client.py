from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from crawlee.storage_clients._base import StorageClient

from ._dataset_client import ApifyDatasetClient
from ._key_value_store_client import ApifyKeyValueStoreClient
from ._request_queue_client import ApifyRequestQueueClient
from apify._utils import docs_group

if TYPE_CHECKING:
    from crawlee.configuration import Configuration


@docs_group('Storage clients')
class ApifyStorageClient(StorageClient):
    """Apify storage client."""

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

        configuration = configuration or ApifyConfiguration.get_global_configuration()
        if isinstance(configuration, ApifyConfiguration):
            return await ApifyDatasetClient.open(id=id, name=name, configuration=configuration)

        raise TypeError(
            f'Expected "configuration" to be an instance of "apify.Configuration", '
            f'but got {type(configuration).__name__} instead.'
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

        configuration = configuration or ApifyConfiguration.get_global_configuration()
        if isinstance(configuration, ApifyConfiguration):
            return await ApifyKeyValueStoreClient.open(id=id, name=name, configuration=configuration)

        raise TypeError(
            f'Expected "configuration" to be an instance of "apify.Configuration", '
            f'but got {type(configuration).__name__} instead.'
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

        configuration = configuration or ApifyConfiguration.get_global_configuration()
        if isinstance(configuration, ApifyConfiguration):
            return await ApifyRequestQueueClient.open(id=id, name=name, configuration=configuration)

        raise TypeError(
            f'Expected "configuration" to be an instance of "apify.Configuration", '
            f'but got {type(configuration).__name__} instead.'
        )
