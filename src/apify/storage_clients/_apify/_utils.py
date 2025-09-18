from __future__ import annotations

import logging
from asyncio import Lock
from logging import getLogger
from typing import TYPE_CHECKING, ClassVar

from apify_client import ApifyClientAsync
from crawlee._utils.crypto import compute_short_hash

from apify._configuration import Configuration

if TYPE_CHECKING:
    from types import TracebackType

    from apify_client.clients import KeyValueStoreClientAsync
    from crawlee.storages import Dataset, KeyValueStore, RequestQueue


logger = getLogger(__name__)


class Alias:
    """Class for handling aliases.

    The purpose of this is class is to ensure that alias storages are created with correct id. This is achieved by using
    default kvs as a storage for global mapping of aliases to storage ids. Same mapping is also kept in memory to avoid
    unnecessary calls to API and also have limited support of alias storages when not running on Apify platform. When on
     Apify platform, the storages created with alias are accessible by the same alias even after migration or reboot.
    """

    _alias_map: ClassVar[dict[str, str]] = {}
    """Map containing pre-existing alias storages and their ids. Global for all instances."""
    _alias_init_lock: Lock | None = None
    """Lock for creating alias storages. Only one alias storage can be created at the time. Global for all instances."""

    _ALIAS_STORAGE_KEY_SEPARATOR = ','
    _ALIAS_MAPPING_KEY = '__STORAGE_ALIASES_MAPPING'

    def __init__(
        self, storage_type: type[Dataset | KeyValueStore | RequestQueue], alias: str, configuration: Configuration
    ) -> None:
        self._storage_type = storage_type
        self._alias = alias
        self._additional_cache_key = self.get_additional_cache_key(configuration)

    async def __aenter__(self) -> Alias:
        """Context manager to prevent race condition in alias creation."""
        lock = await self._get_alias_init_lock()
        await lock.acquire()
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_value: BaseException | None, exc_traceback: TracebackType | None
    ) -> None:
        lock = await self._get_alias_init_lock()
        lock.release()

    @classmethod
    async def _get_alias_init_lock(cls) -> Lock:
        """Get lock for controlling the creation of the alias storages.

        The lock is shared for all instances of the Alias class.
        It is created in async method to ensure that some event loop is already running.
        """
        if cls._alias_init_lock is None:
            cls._alias_init_lock = Lock()
        return cls._alias_init_lock

    @classmethod
    async def get_alias_map(cls) -> dict[str, str]:
        """Get the aliases and storage ids mapping from the default kvs.

        Mapping is loaded from kvs only once and is shared for all instances of the Alias class.

        Returns:
            Map of aliases and storage ids.
        """
        if not cls._alias_map:
            default_kvs_client = await get_default_kvs_client()

            record = await default_kvs_client.get_record(cls.ALIAS_MAPPING_KEY)

            # get_record can return {key: ..., value: ..., content_type: ...}
            if isinstance(record, dict):
                if 'value' in record and isinstance(record['value'], dict):
                    cls._alias_map = record['value']
                else:
                    cls._alias_map = record
            else:
                cls._alias_map = dict[str, str]()

        return cls._alias_map

    @classmethod
    def get_additional_cache_key(cls, configuration: Configuration) -> str:
        """Get additional cache key based on configuration.

        Use only api_public_base_url and token as the relevant for differentiating storages.
        """
        if configuration.api_public_base_url is None or configuration.token is None:
            raise ValueError("'Configuration.api_public_base_url' and 'Configuration.token' must be set.")
        return compute_short_hash(f'{configuration.api_public_base_url}{configuration.token}'.encode())

    @property
    def storage_key(self) -> str:
        """Get a unique storage key used for storing the alias in the mapping."""
        return self.ALIAS_STORAGE_KEY_SEPARATOR.join(
            [
                self.storage_type.__name__,
                self.alias,
                self.additional_cache_key,
            ]
        )

    async def resolve_id(self) -> str | None:
        """Get id of the aliased storage.

        Either locate the id in the in-memory mapping or create the new storage.

        Returns:
            Storage id if it exists, None otherwise.
        """
        return (await self.get_alias_map()).get(self.storage_key, None)

    async def store_mapping(self, storage_id: str) -> None:
        """Add alias and related storage id to the mapping in default kvs and local in-memory mapping."""
        # Update in-memory mapping
        (await self.get_alias_map())[self.storage_key] = storage_id
        if not Configuration.get_global_configuration().is_at_home:
            logging.getLogger(__name__).warning(
                'Alias storage limited retention is only supported on Apify platform. Storage is not exported.'
            )
            return

        default_kvs_client = await get_default_kvs_client()
        await default_kvs_client.get()

        try:
            record = await default_kvs_client.get_record(self.ALIAS_MAPPING_KEY)

            # get_record can return {key: ..., value: ..., content_type: ...}
            if isinstance(record, dict) and 'value' in record:
                record = record['value']

            # Update or create the record with the new alias mapping
            if isinstance(record, dict):
                record[self.storage_key] = storage_id
            else:
                record = {self.storage_key: storage_id}

            # Store the mapping back in the KVS.
            await default_kvs_client.set_record(self.ALIAS_MAPPING_KEY, record)
        except Exception as exc:
            logger.warning(f'Error storing alias mapping for {self.alias}: {exc}')


async def _get_default_kvs_client() -> KeyValueStoreClientAsync:
    """Get a client for the default key-value store."""
    configuration = Configuration.get_global_configuration()

    apify_client_async = ApifyClientAsync(
        token=configuration.token,
        api_url=configuration.api_base_url,
        max_retries=8,
        min_delay_between_retries_millis=500,
        timeout_secs=360,
    )

    return apify_client_async.key_value_store(key_value_store_id=configuration.default_key_value_store_id)
