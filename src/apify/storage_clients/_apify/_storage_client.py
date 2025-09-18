from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from crawlee.storage_clients._base import StorageClient

from ._dataset_client import ApifyDatasetClient
from ._key_value_store_client import ApifyKeyValueStoreClient
from ._request_queue_client_full import ApifyRequestQueueClientFull
from ._request_queue_client_simple import ApifyRequestQueueClientSimple
from ._utils import hash_api_base_url_and_token
from apify import Configuration as ApifyConfiguration
from apify._utils import docs_group

if TYPE_CHECKING:
    from collections.abc import Hashable

    from crawlee.configuration import Configuration as CrawleeConfiguration

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

    # This class breaches Liskov Substitution Principle. It requires specialized Configuration compared to its parent.
    _lsp_violation_error_message_template = (
        'Expected "configuration" to be an instance of "apify.Configuration", but got {} instead.'
    )

    @override
    def get_additional_cache_key(self, configuration: CrawleeConfiguration) -> Hashable:
        if isinstance(configuration, ApifyConfiguration):
            return hash_api_base_url_and_token(configuration)

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
            client: type[ApifyRequestQueueClient] = (
                ApifyRequestQueueClientSimple if (self._simple_request_queue) else ApifyRequestQueueClientFull
            )
            return await client.open(id=id, name=name, alias=alias, configuration=configuration)

        raise TypeError(self._lsp_violation_error_message_template.format(type(configuration).__name__))
