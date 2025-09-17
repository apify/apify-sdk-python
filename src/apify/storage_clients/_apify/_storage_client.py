from __future__ import annotations

import logging
from asyncio import Lock
from typing import TYPE_CHECKING

from typing_extensions import override

from crawlee import service_locator
from crawlee.storage_clients._base import StorageClient

from ._dataset_client import ApifyDatasetClient
from ._key_value_store_client import ApifyKeyValueStoreClient
from ._request_queue_client import ApifyRequestQueueClient
from ._utils import _ALIAS_MAPPING_KEY, _Alias
from apify._configuration import Configuration
from apify._configuration import Configuration as ApifyConfiguration
from apify._utils import docs_group

if TYPE_CHECKING:
    from collections.abc import Hashable

    from crawlee.configuration import Configuration as CrawleeConfiguration


@docs_group('Storage clients')
class ApifyStorageClient(StorageClient):
    """Apify storage client."""

    _alias_storages_initialized = False
    """Flag that indicates whether the pre-existing alias storages were already initialized."""
    _alias_init_lock: Lock | None = None
    """Lock for creating alias storages. Only one alias storage can be created at the time."""

    # This class breaches Liskov Substitution Principle. It requires specialized Configuration compared to its parent.
    _lsp_violation_error_message_template = (
        'Expected "configuration" to be an instance of "apify.Configuration", but got {} instead.'
    )

    @override
    def get_additional_cache_key(self, configuration: CrawleeConfiguration) -> Hashable:
        if isinstance(configuration, ApifyConfiguration):
            if configuration.api_base_url is None or configuration.token is None:
                raise ValueError("'Configuration.api_base_url' and 'Configuration.token' must be set.")
            return _Alias.get_additional_cache_key(configuration.api_base_url, configuration.token)
        raise TypeError(self._lsp_violation_error_message_template.format(type(configuration).__name__))

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
            if alias:
                await self._initialize_alias_storages()
                async with self.get_alias_init_lock():
                    return await ApifyDatasetClient.open(id=id, name=name, alias=alias, configuration=configuration)
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
            if alias:
                await self._initialize_alias_storages()
                async with self.get_alias_init_lock():
                    return await ApifyKeyValueStoreClient.open(
                        id=id, name=name, alias=alias, configuration=configuration
                    )
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
            if alias:
                await self._initialize_alias_storages()
                async with self.get_alias_init_lock():
                    return await ApifyRequestQueueClient.open(
                        id=id, name=name, alias=alias, configuration=configuration
                    )
            return await ApifyRequestQueueClient.open(id=id, name=name, alias=alias, configuration=configuration)

        raise TypeError(self._lsp_violation_error_message_template.format(type(configuration).__name__))

    @classmethod
    def get_alias_init_lock(cls) -> Lock:
        if not cls._alias_init_lock:
            cls._alias_init_lock = Lock()
        return cls._alias_init_lock

    @classmethod
    async def _initialize_alias_storages(cls) -> None:
        """Initialize alias storages.

        This method is called once to populate storage_instance_manager alias related cache. All existing alias
        storages are saved in storage_instance_manager cache. If the alias storage is not there, it does not exist yet.
        """
        if not Configuration.get_global_configuration().is_at_home:
            logging.getLogger(__name__).warning(
                'Alias storage limited retention is only supported on Apify platform. '
                'No pre-existing storages are imported.'
            )
            cls._alias_storages_initialized = True
            return

        async with cls.get_alias_init_lock():
            if cls._alias_storages_initialized:
                return

            cache = service_locator.storage_instance_manager._cache_by_storage_client[ApifyStorageClient]  # noqa: SLF001

            default_kvs_client = await _Alias.get_default_kvs_client()

            record = await default_kvs_client.get_record(key=_ALIAS_MAPPING_KEY)

            if record is not None and 'value' in record:
                # get_record can return {key: ..., value: ..., content_type: ...}
                alias_export_map = record['value']

                for export_key, storage_id in alias_export_map.value.items():
                    exported_alias = _Alias.from_exported_string(export_key)

                    # Re-create custom config used to open the storage
                    custom_config = Configuration()
                    custom_config.api_base_url = exported_alias.api_url
                    custom_config.token = exported_alias.token

                    # Populate the id cache by opening storage by id
                    storage = await exported_alias.storage_type.open(
                        id=storage_id, configuration=custom_config, storage_client=ApifyStorageClient()
                    )
                    # Populate the alias cache as well
                    cache.by_alias[exported_alias.storage_type][exported_alias.alias][
                        exported_alias.additional_cache_key
                    ] = storage

        cls._alias_storages_initialized = True
