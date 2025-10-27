from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from crawlee.storage_clients._base import DatasetClient, KeyValueStoreClient, RequestQueueClient, StorageClient

from apify._configuration import Configuration as ApifyConfiguration
from apify._utils import docs_group
from apify.storage_clients import ApifyStorageClient, FileSystemStorageClient

if TYPE_CHECKING:
    from collections.abc import Hashable

    from crawlee.configuration import Configuration as CrawleeConfiguration


@docs_group('Storage clients')
class SmartApifyStorageClient(StorageClient):
    """Storage client that automatically selects cloud or local storage client based on the environment.

    This storage client provides access to datasets, key-value stores, and request queues by intelligently
    delegating to either the cloud or local storage client based on the execution environment and configuration.

    When running on the Apify platform (which is detected via environment variables), this client automatically
    uses the `cloud_storage_client` to store storage data there. When running locally, it uses the
    `local_storage_client` to store storage data there. You can also force cloud storage usage from your
    local machine by using the `force_cloud` argument.

    This storage client is designed to work specifically in `Actor` context and provides a seamless development
    experience where the same code works both locally and on the Apify platform without any changes.
    """

    def __init__(
        self,
        *,
        cloud_storage_client: StorageClient | None = None,
        local_storage_client: StorageClient | None = None,
    ) -> None:
        """Initialize a new instance.

        Args:
            cloud_storage_client: Storage client used when an Actor is running on the Apify platform, or when
                explicitly enabled via the `force_cloud` argument. Defaults to `ApifyStorageClient`.
            local_storage_client: Storage client used when an Actor is not running on the Apify platform and when
                `force_cloud` flag is not set. Defaults to `FileSystemStorageClient`.
        """
        self._cloud_storage_client = cloud_storage_client or ApifyStorageClient()
        self._local_storage_client = local_storage_client or FileSystemStorageClient()

    def __str__(self) -> str:
        return (
            f'{self.__class__.__name__}(cloud_storage_client={self._cloud_storage_client.__class__.__name__},'
            f' local_storage_client={self._local_storage_client.__class__.__name__})'
        )

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
