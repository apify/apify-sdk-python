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
    """Apify storage client."""

    def __init__(self, *, request_queue_access: Literal['single', 'shared'] = 'single') -> None:
        """Initialize the Apify storage client.

        Args:
            request_queue_access: Controls the implementation of the request queue client based on expected scenario:
                - 'single' is suitable for single consumer scenarios. It makes less API calls, is cheaper and faster.
                - 'shared' is suitable for multiple consumers scenarios at the cost of higher API usage.
                Detailed constraints for the 'single' access type:
                - Only one client is consuming the request queue at the time.
                - Multiple producers can put requests to the queue, but their forefront requests are not guaranteed to
                  be handled so quickly as this client does not aggressively fetch the forefront and relies on local
                  head estimation.
                - Requests are only added to the queue, never deleted by other clients. (Marking as handled is ok.)
                - Other producers can add new requests, but not modify existing ones.
                  (Modifications would not be included in local cache)
        """
        self._request_queue_access = request_queue_access

    # This class breaches Liskov Substitution Principle. It requires specialized Configuration compared to its parent.
    _lsp_violation_error_message_template = (
        'Expected "configuration" to be an instance of "apify.Configuration", but got {} instead.'
    )

    @override
    def get_storage_client_cache_key(self, configuration: CrawleeConfiguration) -> Hashable:
        if isinstance(configuration, ApifyConfiguration):
            # It is not supported to open exactly same queue with 'single' and 'shared' client at the same time.
            # Whichever client variation gets used first, wins.
            return super().get_storage_client_cache_key(configuration), hash_api_base_url_and_token(configuration)

        config_class = type(configuration)
        raise TypeError(
            self._lsp_violation_error_message_template.format(f'{config_class.__module__}.{config_class.__name__}')
        )

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

        raise TypeError(self._lsp_violation_error_message_template.format(type(configuration).__name__))

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

        raise TypeError(self._lsp_violation_error_message_template.format(type(configuration).__name__))

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

        raise TypeError(self._lsp_violation_error_message_template.format(type(configuration).__name__))
