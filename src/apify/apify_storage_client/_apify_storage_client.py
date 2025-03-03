from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from apify_client import ApifyClientAsync
from crawlee._utils.crypto import crypto_random_object_id
from crawlee.storage_clients import StorageClient

from apify._utils import docs_group
from apify.apify_storage_client._dataset_client import DatasetClient
from apify.apify_storage_client._dataset_collection_client import DatasetCollectionClient
from apify.apify_storage_client._key_value_store_client import KeyValueStoreClient
from apify.apify_storage_client._key_value_store_collection_client import KeyValueStoreCollectionClient
from apify.apify_storage_client._request_queue_client import RequestQueueClient
from apify.apify_storage_client._request_queue_collection_client import RequestQueueCollectionClient

if TYPE_CHECKING:
    from apify._configuration import Configuration


@docs_group('Classes')
class ApifyStorageClient(StorageClient):
    """A storage client implementation based on the Apify platform storage."""

    def __init__(self, *, configuration: Configuration) -> None:
        self._client_key = crypto_random_object_id()
        self._apify_client = ApifyClientAsync(
            token=configuration.token,
            api_url=configuration.api_base_url,
            max_retries=8,
            min_delay_between_retries_millis=500,
            timeout_secs=360,
        )
        self._configuration = configuration

    @classmethod
    def from_config(cls, config: Configuration) -> ApifyStorageClient:
        return cls(configuration=config)

    @override
    def dataset(self, id: str) -> DatasetClient:
        return DatasetClient(self._apify_client.dataset(id))

    @override
    def datasets(self) -> DatasetCollectionClient:
        return DatasetCollectionClient(self._apify_client.datasets())

    @override
    def key_value_store(self, id: str) -> KeyValueStoreClient:
        return KeyValueStoreClient(self._apify_client.key_value_store(id), self._configuration.api_public_base_url)

    @override
    def key_value_stores(self) -> KeyValueStoreCollectionClient:
        return KeyValueStoreCollectionClient(self._apify_client.key_value_stores())

    @override
    def request_queue(self, id: str) -> RequestQueueClient:
        return RequestQueueClient(self._apify_client.request_queue(id, client_key=self._client_key))

    @override
    def request_queues(self) -> RequestQueueCollectionClient:
        return RequestQueueCollectionClient(self._apify_client.request_queues())

    @override
    async def purge_on_start(self) -> None:
        pass

    @override
    def get_rate_limit_errors(self) -> dict[int, int]:
        return self._apify_client.stats.rate_limit_errors
