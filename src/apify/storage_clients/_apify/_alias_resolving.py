from __future__ import annotations

import logging
from asyncio import Lock
from logging import getLogger
from typing import TYPE_CHECKING, ClassVar, Literal, overload

from apify_client import ApifyClientAsync

from ._utils import hash_api_base_url_and_token
from apify._configuration import Configuration

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

    from apify_client.clients import (
        DatasetClientAsync,
        DatasetCollectionClientAsync,
        KeyValueStoreClientAsync,
        KeyValueStoreCollectionClientAsync,
        RequestQueueClientAsync,
        RequestQueueCollectionClientAsync,
    )

logger = getLogger(__name__)


@overload
async def open_by_alias(
    *,
    alias: str,
    storage_type: Literal['Dataset'],
    collection_client: DatasetCollectionClientAsync,
    get_resource_client_by_id: Callable[[str], DatasetClientAsync],
    configuration: Configuration,
) -> DatasetClientAsync: ...


@overload
async def open_by_alias(
    *,
    alias: str,
    storage_type: Literal['KeyValueStore'],
    collection_client: KeyValueStoreCollectionClientAsync,
    get_resource_client_by_id: Callable[[str], KeyValueStoreClientAsync],
    configuration: Configuration,
) -> KeyValueStoreClientAsync: ...


@overload
async def open_by_alias(
    *,
    alias: str,
    storage_type: Literal['RequestQueue'],
    collection_client: RequestQueueCollectionClientAsync,
    get_resource_client_by_id: Callable[[str], RequestQueueClientAsync],
    configuration: Configuration,
) -> RequestQueueClientAsync: ...


async def open_by_alias(
    *,
    alias: str,
    storage_type: Literal['Dataset', 'KeyValueStore', 'RequestQueue'],
    collection_client: (
        KeyValueStoreCollectionClientAsync | RequestQueueCollectionClientAsync | DatasetCollectionClientAsync
    ),
    get_resource_client_by_id: Callable[[str], KeyValueStoreClientAsync | RequestQueueClientAsync | DatasetClientAsync],
    configuration: Configuration,
) -> KeyValueStoreClientAsync | RequestQueueClientAsync | DatasetClientAsync:
    """Open storage by alias, creating it if necessary.

    This function resolves storage aliases to their IDs, creating new unnamed storage if needed.
    The alias mapping is stored in the default key-value store for persistence across Actor runs.

    Args:
        alias: The alias name for the storage (e.g., '__default__', 'my-storage').
        storage_type: The type of storage to open.
        collection_client: The Apify API collection client for the storage type.
        get_resource_client_by_id: A callable that takes a storage ID and returns the resource client.
        configuration: Configuration object containing API credentials and settings.

    Returns:
        The storage client for the opened or created storage.

    Raises:
        ValueError: If storage ID cannot be determined from API response.
        TypeError: If API response format is unexpected.
    """
    async with AliasResolver(
        storage_type=storage_type,
        alias=alias,
        configuration=configuration,
    ) as alias_resolver:
        storage_id = await alias_resolver.resolve_id()

        if storage_id:
            # Check if storage with this ID exists
            resource_client = get_resource_client_by_id(storage_id)
            raw_metadata = await resource_client.get()
            if raw_metadata:
                return resource_client

        # Create new unnamed storage and store alias mapping
        raw_metadata = await collection_client.get_or_create()

        await alias_resolver.store_mapping(storage_id=raw_metadata['id'])
        return get_resource_client_by_id(raw_metadata['id'])


class AliasResolver:
    """Class for handling aliases.

    The purpose of this is class is to ensure that alias storages are created with correct id. This is achieved by using
    default kvs as a storage for global mapping of aliases to storage ids. Same mapping is also kept in memory to avoid
    unnecessary calls to API and also have limited support of alias storages when not running on Apify platform. When on
    Apify platform, the storages created with alias are accessible by the same alias even after migration or reboot.
    """

    _ALIAS_MAPPING_KEY = '__STORAGE_ALIASES_MAPPING'
    """Key used for storing the alias mapping in the default kvs."""

    _ALIAS_STORAGE_KEY_SEPARATOR = ','
    """Separator used in the storage key for storing the alias mapping."""

    _alias_map: ClassVar[dict[str, str]] = {}
    """Map containing pre-existing alias storages and their ids. Global for all instances."""

    _alias_init_lock: Lock | None = None
    """Lock for creating alias storages. Only one alias storage can be created at the time. Global for all instances."""

    def __init__(
        self,
        storage_type: Literal['Dataset', 'KeyValueStore', 'RequestQueue'],
        alias: str,
        configuration: Configuration,
    ) -> None:
        self._alias = alias
        self._configuration = configuration
        self._storage_key = self.get_storage_key(
            storage_type=storage_type, alias=alias, additional_cache_key=hash_api_base_url_and_token(configuration)
        )

    async def __aenter__(self) -> AliasResolver:
        """Context manager to prevent race condition in alias creation."""
        lock = await self._get_alias_init_lock()
        await lock.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        lock = await self._get_alias_init_lock()
        lock.release()

    @classmethod
    async def _get_alias_init_lock(cls) -> Lock:
        """Get lock for controlling the creation of the alias storages.

        The lock is shared for all instances of the AliasResolver class.
        It is created in async method to ensure that some event loop is already running.
        """
        if cls._alias_init_lock is None:
            cls._alias_init_lock = Lock()
        return cls._alias_init_lock

    @classmethod
    async def _get_alias_map(cls, configuration: Configuration) -> dict[str, str]:
        """Get the aliases and storage ids mapping from the default kvs.

        Mapping is loaded from kvs only once and is shared for all instances of the _AliasResolver class.

        Args:
            configuration: Configuration object to use for accessing the default KVS.

        Returns:
            Map of aliases and storage ids.
        """
        if not cls._alias_map and Configuration.get_global_configuration().is_at_home:
            default_kvs_client = await cls._get_default_kvs_client(configuration)

            record = await default_kvs_client.get_record(cls._ALIAS_MAPPING_KEY)
            cls._alias_map = record.get('value', {}) if record else {}

        return cls._alias_map

    async def resolve_id(self) -> str | None:
        """Get id of the aliased storage.

        Returns:
            Storage id if it exists, None otherwise.
        """
        return (await self._get_alias_map(self._configuration)).get(self._storage_key, None)

    async def store_mapping(self, storage_id: str) -> None:
        """Add alias and related storage id to the mapping in default kvs and local in-memory mapping."""
        # Update in-memory mapping
        alias_map = await self._get_alias_map(self._configuration)
        alias_map[self._storage_key] = storage_id

        if not Configuration.get_global_configuration().is_at_home:
            logging.getLogger(__name__).debug(
                '_AliasResolver storage limited retention is only supported on Apify platform. Storage is not exported.'
            )
            return

        default_kvs_client = await self._get_default_kvs_client(self._configuration)
        await default_kvs_client.get()

        try:
            record = await default_kvs_client.get_record(self._ALIAS_MAPPING_KEY)
            value = record.get('value', {}) if record else {}
            value[self._storage_key] = storage_id

            # Store the mapping back in the KVS.
            await default_kvs_client.set_record(key=self._ALIAS_MAPPING_KEY, value=value)
        except Exception as exc:
            logger.warning(f'Error storing alias mapping for {self._alias}: {exc}')

    @staticmethod
    async def _get_default_kvs_client(configuration: Configuration) -> KeyValueStoreClientAsync:
        """Get a client for the default key-value store."""
        apify_client_async = ApifyClientAsync(
            token=configuration.token,
            api_url=configuration.api_base_url,
            max_retries=8,
            min_delay_between_retries_millis=500,
            timeout_secs=360,
        )

        if not configuration.default_key_value_store_id:
            raise ValueError("'Configuration.default_key_value_store_id' must be set.")

        return apify_client_async.key_value_store(key_value_store_id=configuration.default_key_value_store_id)

    @classmethod
    def get_storage_key(
        cls, storage_type: Literal['Dataset', 'KeyValueStore', 'RequestQueue'], alias: str, additional_cache_key: str
    ) -> str:
        return cls._ALIAS_STORAGE_KEY_SEPARATOR.join(
            [
                storage_type,
                alias,
                additional_cache_key,
            ]
        )

    @classmethod
    async def register_aliases(cls, configuration: Configuration) -> None:
        """Load alias mapping from configuration to the default kvs."""
        async with await cls._get_alias_init_lock():
            # Skip if no mapping or just default storages
            if configuration.actor_storages is None or set(
                configuration.actor_storages.datasets.keys()
                | configuration.actor_storages.key_value_stores.keys()
                | configuration.actor_storages.request_queues.keys()
            ) == {'default'}:
                return

            configuration_mapping = {}

            if configuration.default_dataset_id != configuration.actor_storages.datasets.get('default'):
                logger.warning(
                    f'Conflicting default dataset ids: {configuration.default_dataset_id=},'
                    f" {configuration.actor_storages.datasets.get('default')=}"
                )
            additional_cache_key = hash_api_base_url_and_token(configuration)

            for mapping, storage_type in (
                (configuration.actor_storages.key_value_stores, 'KeyValueStore'),
                (configuration.actor_storages.datasets, 'Dataset'),
                (configuration.actor_storages.request_queues, 'RequestQueue'),
            ):
                for storage_alias, storage_id in mapping.items():
                    configuration_mapping[
                        cls.get_storage_key(
                            storage_type,
                            '__default__' if storage_alias == 'default' else storage_alias,
                            additional_cache_key,
                        )
                    ] = storage_id

            # Bulk update the mapping in the default KVS with the configuration mapping.
            client = await cls._get_default_kvs_client(configuration=configuration)
            record = await client.get_record(cls._ALIAS_MAPPING_KEY)
            existing_mapping = record.get('value', {}) if record else {}

            # Update the existing mapping with the configuration mapping.
            existing_mapping.update(configuration_mapping)
            # Store the updated mapping back in the KVS and in memory.
            await client.set_record(cls._ALIAS_MAPPING_KEY, existing_mapping)
            cls._alias_map.update(existing_mapping)
