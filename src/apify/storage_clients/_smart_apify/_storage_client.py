from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from crawlee.storage_clients._base import DatasetClient, KeyValueStoreClient, RequestQueueClient, StorageClient

from apify._configuration import Configuration as ApifyConfiguration
from apify._utils import docs_group
from apify.storage_clients import ApifyStorageClient
from apify.storage_clients._file_system import ApifyFileSystemStorageClient

if TYPE_CHECKING:
    from collections.abc import Hashable

    from crawlee.configuration import Configuration as CrawleeConfiguration


@docs_group('Storage clients')
class SmartApifyStorageClient(StorageClient):
    """SmartApifyStorageClient that delegates to cloud_storage_client or local_storage_client.

    When running on Apify platform use cloud_storage_client, else use local_storage_client. This storage client is
    designed to work specifically in Actor context.
    """

    def __init__(
        self,
        *,
        cloud_storage_client: ApifyStorageClient | None = None,
        local_storage_client: StorageClient | None = None,
    ) -> None:
        """Initialize the Apify storage client.

        Args:
            cloud_storage_client: Client used to communicate with the Apify platform storage. Either through
                `force_cloud` argument when opening storages or automatically when running on the Apify platform.
            local_storage_client: Client used to communicate with the storage when not running on the Apify
                platform and not using `force_cloud` argument when opening storages.
        """
        self._cloud_storage_client = cloud_storage_client or ApifyStorageClient(request_queue_access='single')
        self._local_storage_client = local_storage_client or ApifyFileSystemStorageClient()

    def __str__(self) -> str:
        return (
            f'{self.__class__.__name__}(cloud_storage_client={self._cloud_storage_client.__class__.__name__},'
            f' local_storage_client={self._local_storage_client.__class__.__name__})'
        )

    def get_suitable_storage_client(self, *, force_cloud: bool = False) -> StorageClient:
        """Get a suitable storage client based on the global configuration and the value of the force_cloud flag.

        Args:
            force_cloud: If True, return `cloud_storage_client`.
        """
        if ApifyConfiguration.get_global_configuration().is_at_home:
            return self._cloud_storage_client

        configuration = ApifyConfiguration.get_global_configuration()
        if force_cloud:
            if configuration.token is None:
                raise RuntimeError(
                    'In order to use the Apify cloud storage from your computer, '
                    'you need to provide an Apify token using the APIFY_TOKEN environment variable.'
                )
            return self._cloud_storage_client

        return self._local_storage_client

    @override
    def get_storage_client_cache_key(self, configuration: CrawleeConfiguration) -> Hashable:
        if ApifyConfiguration.get_global_configuration().is_at_home:
            if isinstance(configuration, ApifyConfiguration):
                return self._cloud_storage_client.get_storage_client_cache_key(configuration)
            raise TypeError('Expecting ApifyConfiguration')

        return self._local_storage_client.get_storage_client_cache_key(configuration)

    @override
    async def create_dataset_client(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        alias: str | None = None,
        configuration: CrawleeConfiguration | None = None,
    ) -> DatasetClient:
        return await self.get_suitable_storage_client().create_dataset_client(
            id=id, name=id, alias=alias, configuration=configuration
        )

    @override
    async def create_kvs_client(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        alias: str | None = None,
        configuration: CrawleeConfiguration | None = None,
    ) -> KeyValueStoreClient:
        return await self.get_suitable_storage_client().create_kvs_client(
            id=id, name=id, alias=alias, configuration=configuration
        )

    @override
    async def create_rq_client(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        alias: str | None = None,
        configuration: CrawleeConfiguration | None = None,
    ) -> RequestQueueClient:
        return await self.get_suitable_storage_client().create_rq_client(
            id=id, name=id, alias=alias, configuration=configuration
        )
