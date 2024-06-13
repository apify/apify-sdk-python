from apify_client import ApifyClientAsync
from crawlee.base_storage_client.base_storage_client import BaseStorageClient
from typing_extensions import override

from .dataset_client import DatasetClient
from .dataset_collection_client import DatasetCollectionClient
from .key_value_store_client import KeyValueStoreClient
from .key_value_store_collection_client import KeyValueStoreCollectionClient
from .request_queue_client import RequestQueueClient
from .request_queue_collection_client import RequestQueueCollectionClient
from apify.config import Configuration


class ApifyStorageClient(BaseStorageClient):
    """A storage client implementation based on the Apify platform storage."""

    def __init__(self, *, configuration: Configuration) -> None:
        self._apify_client = ApifyClientAsync(
            token=configuration.token,
            api_url=configuration.api_base_url,
            max_retries=8,  # TODO
            min_delay_between_retries_millis=500,
            timeout_secs=360,
        )

    @override
    def dataset(self, id: str) -> DatasetClient:  # noqa: A002
        return DatasetClient(self._apify_client.dataset(id))

    @override
    def datasets(self) -> DatasetCollectionClient:
        return DatasetCollectionClient(self._apify_client.datasets())

    @override
    def key_value_store(self, id: str) -> KeyValueStoreClient:
        return KeyValueStoreClient(self._apify_client.key_value_store(id))

    @override
    def key_value_stores(self) -> KeyValueStoreCollectionClient:
        return KeyValueStoreCollectionClient(self._apify_client.key_value_stores())

    @override
    def request_queue(self, id: str) -> RequestQueueClient:
        return RequestQueueClient(self._apify_client.request_queue(id))

    @override
    def request_queues(self) -> RequestQueueCollectionClient:
        return RequestQueueCollectionClient(self._apify_client.request_queues())

    @override
    async def purge_on_start(self) -> None:
        pass