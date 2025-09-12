from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from crawlee.storage_clients._base import StorageClient

from ._dataset_client import ApifyDatasetClient
from ._key_value_store_client import ApifyKeyValueStoreClient
from ._request_queue_client_full import ApifyRequestQueueClientFull
from ._request_queue_client_simple import ApifyRequestQueueClientSimple
from apify._utils import docs_group

if TYPE_CHECKING:
    from crawlee.configuration import Configuration

    from ._request_queue_client import ApifyRequestQueueClient


@docs_group('Storage clients')
class ApifyStorageClient(StorageClient):
    """Apify storage client."""

    def __init__(self, *, simple_request_queue: bool = True) -> None:
        """Initialize the Apify storage client.

        Args:
            simple_request_queue: If True, the `create_rq_client` will always return `ApifyRequestQueueClientSimple`,
                if false it will return `ApifyRequestQueueClientFull`. Simple client is suitable for single consumer
                scenarios and makes less API calls. Full client is suitable for multiple consumers scenarios at the
                cost of higher API usage
        """
        self._simple_request_queue = simple_request_queue

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
            if self._simple_request_queue:
                return await ApifyRequestQueueClientSimple.open(id=id, name=name, configuration=configuration)
            return await ApifyRequestQueueClientFull.open(id=id, name=name, configuration=configuration)

        raise TypeError(
            f'Expected "configuration" to be an instance of "apify.Configuration", '
            f'but got {type(configuration).__name__} instead.'
        )
