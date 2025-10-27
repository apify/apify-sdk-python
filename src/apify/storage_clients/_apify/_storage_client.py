from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from typing_extensions import override

from crawlee.storage_clients._base import StorageClient

from ._dataset_client import ApifyDatasetClient
from ._key_value_store_client import ApifyKeyValueStoreClient
from ._request_queue_client import ApifyRequestQueueClient
from ._utils import hash_api_base_url_and_token
from apify._configuration import Configuration as ApifyConfiguration
from apify._utils import docs_group

if TYPE_CHECKING:
    from collections.abc import Hashable

    from crawlee.configuration import Configuration as CrawleeConfiguration


@docs_group('Storage clients')
class ApifyStorageClient(StorageClient):
    """Apify platform implementation of the storage client.

    This storage client provides access to datasets, key-value stores, and request queues that persist data
    to the Apify platform. Each storage type is implemented with its own specific Apify client that stores data
    in the cloud, making it accessible from anywhere.

    The communication with the Apify platform is handled via the Apify API client for Python, which is an HTTP API
    wrapper. For maximum efficiency and performance of the storage clients, various caching mechanisms are used to
    minimize the number of API calls made to the Apify platform. Data can be inspected and manipulated through
    the Apify console web interface or via the Apify API.

    The request queue client supports two access modes controlled by the `request_queue_access` parameter:

    ### Single mode

    The `single` mode is optimized for scenarios with only one consumer. It minimizes API calls, making it faster
    and more cost-efficient compared to the `shared` mode. This option is ideal when a single Actor is responsible
    for consuming the entire request queue. Using multiple consumers simultaneously may lead to inconsistencies
    or unexpected behavior.

    In this mode, multiple producers can safely add new requests, but forefront requests may not be processed
    immediately, as the client relies on local head estimation instead of frequent forefront fetching. Requests can
    also be added or marked as handled by other clients, but they must not be deleted or modified, since such changes
    would not be reflected in the local cache. If a request is already fully cached locally, marking it as handled
    by another client will be ignored by this client. This does not cause errors but can occasionally result in
    reprocessing a request that was already handled elsewhere. If the request was not yet cached locally, marking
    it as handled poses no issue.

    ### Shared mode

    The `shared` mode is designed for scenarios with multiple concurrent consumers. It ensures proper synchronization
    and consistency across clients, at the cost of higher API usage and slightly worse performance. This mode is safe
    for concurrent access from multiple processes, including Actors running in parallel on the Apify platform. It
    should be used when multiple consumers need to process requests from the same queue simultaneously.
    """

    _LSP_ERROR_MSG = 'Expected "configuration" to be an instance of "apify.Configuration", but got {} instead.'
    """This class (intentionally) violates the Liskov Substitution Principle.

    It requires a specialized `Configuration` instance compared to its parent class.
    """

    def __init__(self, *, request_queue_access: Literal['single', 'shared'] = 'single') -> None:
        """Initialize a new instance.

        Args:
            request_queue_access: Defines how the request queue client behaves. Use `single` mode for a single
                consumer. It has fewer API calls, meaning better performance and lower costs. If you need multiple
                concurrent consumers use `shared` mode, but expect worse performance and higher costs due to
                the additional overhead.
        """
        self._request_queue_access = request_queue_access

    @override
    async def create_dataset_client(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        alias: str | None = None,
        configuration: CrawleeConfiguration | None = None,
    ) -> ApifyDatasetClient:
        configuration = configuration or ApifyConfiguration.get_global_configuration()
        if isinstance(configuration, ApifyConfiguration):
            return await ApifyDatasetClient.open(id=id, name=name, alias=alias, configuration=configuration)

        raise TypeError(self._LSP_ERROR_MSG.format(type(configuration).__name__))

    @override
    async def create_kvs_client(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        alias: str | None = None,
        configuration: CrawleeConfiguration | None = None,
    ) -> ApifyKeyValueStoreClient:
        configuration = configuration or ApifyConfiguration.get_global_configuration()
        if isinstance(configuration, ApifyConfiguration):
            return await ApifyKeyValueStoreClient.open(id=id, name=name, alias=alias, configuration=configuration)

        raise TypeError(self._LSP_ERROR_MSG.format(type(configuration).__name__))

    @override
    async def create_rq_client(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        alias: str | None = None,
        configuration: CrawleeConfiguration | None = None,
    ) -> ApifyRequestQueueClient:
        configuration = configuration or ApifyConfiguration.get_global_configuration()
        if isinstance(configuration, ApifyConfiguration):
            return await ApifyRequestQueueClient.open(
                id=id, name=name, alias=alias, configuration=configuration, access=self._request_queue_access
            )

        raise TypeError(self._LSP_ERROR_MSG.format(type(configuration).__name__))

    @override
    def get_storage_client_cache_key(self, configuration: CrawleeConfiguration) -> Hashable:
        if isinstance(configuration, ApifyConfiguration):
            # It is not supported to open exactly same queue with 'single' and 'shared' client at the same time.
            # Whichever client variation gets used first, wins.
            return super().get_storage_client_cache_key(configuration), hash_api_base_url_and_token(configuration)

        config_class = type(configuration)
        raise TypeError(self._LSP_ERROR_MSG.format(f'{config_class.__module__}.{config_class.__name__}'))
