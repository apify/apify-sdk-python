from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

from typing_extensions import override

from crawlee.storage_clients._base import DatasetClient, KeyValueStoreClient, RequestQueueClient, StorageClient
from crawlee.storages import RequestQueue

from apify._configuration import Configuration as ApifyConfiguration
from apify._utils import docs_group
from apify.storage_clients import ApifyStorageClient
from apify.storage_clients._file_system import ApifyFileSystemStorageClient
from apify.storages import Dataset, KeyValueStore

if TYPE_CHECKING:
    from collections.abc import Hashable

    from crawlee.configuration import Configuration as CrawleeConfiguration


@docs_group('Storage clients')
class ApifyHybridStorageClient(StorageClient):
    """ApifyHybridStorageClient that delegates to cloud_storage_client or local_storage_client.

    When running on Apify platform use cloud_storage_client, else use local_storage_client. It has additional wrapper
    methods with `force_cloud` parameter to force using cloud_storage_client when opening specific storages even when
    not running on the Apify platform. This storage client is designed to work specifically in Actor context.
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

    def _get_suitable_storage_client(self, *, force_cloud: bool = False) -> StorageClient:
        if self._is_at_home:
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
    def get_additional_cache_key(self, configuration: CrawleeConfiguration) -> Hashable:
        if self._is_at_home:
            if isinstance(configuration, ApifyConfiguration):
                return self._cloud_storage_client.get_additional_cache_key(configuration)
            raise TypeError('Expecting ApifyConfiguration')

        return self._local_storage_client.get_additional_cache_key(configuration)

    @override
    async def create_dataset_client(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        alias: str | None = None,
        configuration: CrawleeConfiguration | None = None,
    ) -> DatasetClient:
        return await self._get_suitable_storage_client().create_dataset_client(
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
        return await self._get_suitable_storage_client().create_kvs_client(
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
        return await self._get_suitable_storage_client().create_rq_client(
            id=id, name=id, alias=alias, configuration=configuration
        )

    async def open_dataset(
        self,
        *,
        id: str | None = None,
        alias: str | None = None,
        name: str | None = None,
        configuration: ApifyConfiguration | None = None,
        force_cloud: bool = False,
    ) -> Dataset:
        """Open a dataset.

        Datasets are used to store structured data where each object stored has the same attributes, such as online
        store products or real estate offers. The actual data is stored either on the local filesystem or in
        the Apify cloud.

        Args:
            id: The ID of the dataset to open. If provided, searches for existing dataset by ID.
                Mutually exclusive with name and alias.
            name: The name of the dataset to open (global scope, persists across runs).
                Mutually exclusive with id and alias.
            alias: The alias of the dataset to open (run scope, creates unnamed storage).
                Mutually exclusive with id and name.
            configuration: Configuration used to open the dataset.
            force_cloud: If set to `True` then the Apify cloud storage is always used. This way it is possible
                to combine local and cloud storage.

        Returns:
            An instance of the `Dataset` class for the given ID or name.
        """
        return await Dataset.open(
            id=id,
            alias=alias,
            name=name,
            configuration=configuration,
            storage_client=self._get_suitable_storage_client(force_cloud=force_cloud),
        )

    async def open_key_value_store(
        self,
        *,
        id: str | None = None,
        alias: str | None = None,
        name: str | None = None,
        configuration: ApifyConfiguration | None = None,
        force_cloud: bool = False,
    ) -> KeyValueStore:
        """Open a key-value store.

        Key-value stores are used to store records or files, along with their MIME content type. The records are stored
        and retrieved using a unique key. The actual data is stored either on a local filesystem or in the Apify cloud.

        Args:
            id: The ID of the KVS to open. If provided, searches for existing KVS by ID.
                Mutually exclusive with name and alias.
            name: The name of the KVS to open (global scope, persists across runs).
                Mutually exclusive with id and alias.
            alias: The alias of the KVS to open (run scope, creates unnamed storage).
                Mutually exclusive with id and name.
            configuration: Configuration used to open the key value store.
            force_cloud: If set to `True` then the Apify cloud storage is always used. This way it is possible
                to combine local and cloud storage.

        Returns:
            An instance of the `KeyValueStore` class for the given ID or name.
        """
        return await KeyValueStore.open(
            id=id,
            alias=alias,
            name=name,
            configuration=configuration,
            storage_client=self._get_suitable_storage_client(force_cloud=force_cloud),
        )

    async def open_request_queue(
        self,
        *,
        id: str | None = None,
        alias: str | None = None,
        name: str | None = None,
        configuration: ApifyConfiguration | None = None,
        force_cloud: bool = False,
    ) -> RequestQueue:
        """Open a request queue.

        Request queue represents a queue of URLs to crawl, which is stored either on local filesystem or in
        the Apify cloud. The queue is used for deep crawling of websites, where you start with several URLs and then
        recursively follow links to other pages. The data structure supports both breadth-first and depth-first
        crawling orders.

        Args:
            id: The ID of the RQ to open. If provided, searches for existing RQ by ID.
                Mutually exclusive with name and alias.
            name: The name of the RQ to open (global scope, persists across runs).
                Mutually exclusive with id and alias.
            alias: The alias of the RQ to open (run scope, creates unnamed storage).
                Mutually exclusive with id and name.
            configuration: Configuration used to open the request queue.
            force_cloud: If set to `True` then the Apify cloud storage is always used. This way it is possible
                to combine local and cloud storage.

        Returns:
            An instance of the `RequestQueue` class for the given ID or name.
        """
        return await RequestQueue.open(
            id=id,
            alias=alias,
            name=name,
            configuration=configuration,
            storage_client=self._get_suitable_storage_client(force_cloud=force_cloud),
        )

    @cached_property
    def _is_at_home(self) -> bool:
        configuration = ApifyConfiguration.get_global_configuration()
        return configuration.is_at_home
