from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from asyncio import Lock
from base64 import b64encode
from hashlib import sha256
from logging import getLogger
from typing import TYPE_CHECKING, ClassVar, Generic, TypeVar

from apify_client import ApifyClientAsync
from apify_client.clients import (
    DatasetClientAsync,
    DatasetCollectionClientAsync,
    KeyValueStoreClientAsync,
    KeyValueStoreCollectionClientAsync,
    RequestQueueClientAsync,
    RequestQueueCollectionClientAsync,
)
from crawlee._utils.crypto import compute_short_hash
from crawlee.storage_clients.models import (
    DatasetMetadata,
    KeyValueStoreMetadata,
    RequestQueueMetadata,
)

from apify._configuration import Configuration
from apify.storage_clients._apify._models import ApifyKeyValueStoreMetadata

if TYPE_CHECKING:
    from types import TracebackType

    from crawlee.storages._base import Storage


logger = getLogger(__name__)

ResourceCollectionClient = (
    KeyValueStoreCollectionClientAsync | RequestQueueCollectionClientAsync | DatasetCollectionClientAsync
)
TResourceClient = TypeVar(
    'TResourceClient', bound=KeyValueStoreClientAsync | RequestQueueClientAsync | DatasetClientAsync
)
TStorageMetadata = TypeVar('TStorageMetadata', bound=KeyValueStoreMetadata | RequestQueueMetadata | DatasetMetadata)


class AliasResolver:
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

    def __init__(self, storage_type: type[Storage], alias: str, configuration: Configuration) -> None:
        self._storage_type = storage_type
        self._alias = alias
        self._additional_cache_key = hash_api_base_url_and_token(configuration)

    async def __aenter__(self) -> AliasResolver:
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

        The lock is shared for all instances of the AliasResolver class.
        It is created in async method to ensure that some event loop is already running.
        """
        if cls._alias_init_lock is None:
            cls._alias_init_lock = Lock()
        return cls._alias_init_lock

    @classmethod
    async def _get_alias_map(cls) -> dict[str, str]:
        """Get the aliases and storage ids mapping from the default kvs.

        Mapping is loaded from kvs only once and is shared for all instances of the AliasResolver class.

        Returns:
            Map of aliases and storage ids.
        """
        if not cls._alias_map and Configuration.get_global_configuration().is_at_home:
            default_kvs_client = await _get_default_kvs_client()

            record = await default_kvs_client.get_record(cls._ALIAS_MAPPING_KEY)

            # get_record can return {key: ..., value: ..., content_type: ...}
            if isinstance(record, dict):
                if 'value' in record and isinstance(record['value'], dict):
                    cls._alias_map = record['value']
                else:
                    cls._alias_map = record
            else:
                cls._alias_map = dict[str, str]()

        return cls._alias_map

    async def resolve_id(self) -> str | None:
        """Get id of the aliased storage.

        Returns:
            Storage id if it exists, None otherwise.
        """
        return (await self._get_alias_map()).get(self._storage_key, None)

    async def store_mapping(self, storage_id: str) -> None:
        """Add alias and related storage id to the mapping in default kvs and local in-memory mapping."""
        # Update in-memory mapping
        (await self._get_alias_map())[self._storage_key] = storage_id
        if not Configuration.get_global_configuration().is_at_home:
            logging.getLogger(__name__).debug(
                'AliasResolver storage limited retention is only supported on Apify platform. Storage is not exported.'
            )
            return

        default_kvs_client = await _get_default_kvs_client()
        await default_kvs_client.get()

        try:
            record = await default_kvs_client.get_record(self._ALIAS_MAPPING_KEY)

            # get_record can return {key: ..., value: ..., content_type: ...}
            if isinstance(record, dict) and 'value' in record:
                record = record['value']

            # Update or create the record with the new alias mapping
            if isinstance(record, dict):
                record[self._storage_key] = storage_id
            else:
                record = {self._storage_key: storage_id}

            # Store the mapping back in the KVS.
            await default_kvs_client.set_record(self._ALIAS_MAPPING_KEY, record)
        except Exception as exc:
            logger.warning(f'Error storing alias mapping for {self._alias}: {exc}')

    @property
    def _storage_key(self) -> str:
        """Get a unique storage key used for storing the alias in the mapping."""
        return self._ALIAS_STORAGE_KEY_SEPARATOR.join(
            [
                self._storage_type.__name__,
                self._alias,
                self._additional_cache_key,
            ]
        )


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
    if not configuration.default_key_value_store_id:
        raise ValueError("'Configuration.default_key_value_store_id' must be set.")
    return apify_client_async.key_value_store(key_value_store_id=configuration.default_key_value_store_id)


def hash_api_base_url_and_token(configuration: Configuration) -> str:
    """Hash configuration.api_public_base_url and configuration.token in deterministic way."""
    if configuration.api_public_base_url is None or configuration.token is None:
        raise ValueError("'Configuration.api_public_base_url' and 'Configuration.token' must be set.")
    return compute_short_hash(f'{configuration.api_public_base_url}{configuration.token}'.encode())


def unique_key_to_request_id(unique_key: str, *, request_id_length: int = 15) -> str:
    """Generate a deterministic request ID based on a unique key.

    Args:
        unique_key: The unique key to convert into a request ID.
        request_id_length: The length of the request ID.

    Returns:
        A URL-safe, truncated request ID based on the unique key.
    """
    # Encode the unique key and compute its SHA-256 hash
    hashed_key = sha256(unique_key.encode('utf-8')).digest()

    # Encode the hash in base64 and decode it to get a string
    base64_encoded = b64encode(hashed_key).decode('utf-8')

    # Remove characters that are not URL-safe ('+', '/', or '=')
    url_safe_key = re.sub(r'(\+|\/|=)', '', base64_encoded)

    # Truncate the key to the desired length
    return url_safe_key[:request_id_length]


def create_apify_client(configuration: Configuration) -> ApifyClientAsync:
    """Create and return an ApifyClientAsync instance using the provided configuration."""
    if not configuration.token:
        raise ValueError(f'Apify storage client requires a valid token in Configuration (token={configuration.token}).')

    api_url = configuration.api_base_url
    if not api_url:
        raise ValueError(f'Apify storage client requires a valid API URL in Configuration (api_url={api_url}).')

    api_public_base_url = configuration.api_public_base_url
    if not api_public_base_url:
        raise ValueError(
            'Apify storage client requires a valid API public base URL in Configuration '
            f'(api_public_base_url={api_public_base_url}).'
        )

    # Create Apify client with the provided token and API URL.
    return ApifyClientAsync(
        token=configuration.token,
        api_url=api_url,
        api_public_url=api_public_base_url,
        max_retries=8,
        min_delay_between_retries_millis=500,
        timeout_secs=360,
    )


class ApiClientFactory(ABC, Generic[TResourceClient, TStorageMetadata]):
    def __init__(self, configuration: Configuration, alias: str | None, name: str | None, id: str | None) -> None:
        if sum(1 for param in [id, name, alias] if param is not None) > 1:
            raise ValueError('Only one of "id", "name", or "alias" can be specified, not multiple.')

        self._alias = alias
        self._name = name
        self._id = id
        self._configuration = configuration
        self._api_client = create_apify_client(configuration)

    async def get_client_with_metadata(self) -> tuple[TResourceClient, TStorageMetadata]:
        match (self._alias, self._name, self._id, self._default_id):
            case (None, None, None, None):
                # Normalize unnamed default storage in cases where not defined in `self._default_id` to
                # unnamed storage aliased as `__default__`. Used only when running locally.
                return await self._open_by_alias('__default__')

            case (str(), None, None, _):
                return await self._open_by_alias(self._alias)

            case (None, None, None, str()):
                resource_client = self._get_resource_client(id=self._default_id)
                raw_metadata = await resource_client.get()
                metadata = self._get_metadata(raw_metadata)
                if not raw_metadata:
                    # Do we want this??? Backwards compatibility, so probably yes.
                    # Default storage does not exist. Create a new one with new id.
                    raw_metadata = await self._collection_client.get_or_create()
                    metadata = self._get_metadata(raw_metadata)
                    resource_client = self._get_resource_client(id=metadata.id)
                return resource_client, metadata

            case (None, str(), None, _):
                metadata = self._get_metadata(await self._collection_client.get_or_create(name=self._name))
                # Freshly fetched named storage. No need to fetch it again.
                return self._get_resource_client(id=metadata.id), metadata

            case (None, None, str(), _):
                resource_client = self._get_resource_client(id=self._id)
                # Fetch its metadata.
                raw_metadata = await resource_client.get()
                # If metadata is None, it means the storage does not exist.
                if raw_metadata is None:
                    raise ValueError(f'Opening {self._storage_type} with id={self._id} failed.')
                return resource_client, self._get_metadata(raw_metadata)

        raise RuntimeError('Unreachable code')

    @property
    @abstractmethod
    def _collection_client(self) -> ResourceCollectionClient:
        """Get a collection API client."""

    @property
    @abstractmethod
    def _default_id(self) -> str | None:
        """Get a metadata model class."""

    @property
    @abstractmethod
    def _storage_type(self) -> type[Storage]:
        """Get a metadata model class."""

    @staticmethod
    @abstractmethod
    def _get_metadata(raw_metadata: dict | None) -> TStorageMetadata:
        """Get a metadata model class."""

    async def _open_by_alias(self, alias: str) -> tuple[TResourceClient, TStorageMetadata]:
        # Check if there is pre-existing alias mapping in the default KVS.
        async with AliasResolver(
            storage_type=self._storage_type, alias=alias, configuration=self._configuration
        ) as _alias:
            id = await _alias.resolve_id()

            if id:
                # There was id, storage has to exist, fetch metadata to confirm it.
                resource_client = self._get_resource_client(id=id)
                raw_metadata = await resource_client.get()
                if raw_metadata:
                    return resource_client, self._get_metadata(raw_metadata)
                # If we do not raise here, we will behave same as for default storage. We create it even though it
                # should exist already. Consistency or throw an error???

            # There was no pre-existing alias in the mapping or the id did not point to existing storage.
            # Create a new unnamed storage and store the alias mapping.
            raw_metadata = await self._collection_client.get_or_create()
            metadata = ApifyKeyValueStoreMetadata.model_validate(raw_metadata)
            await _alias.store_mapping(storage_id=metadata.id)

            # Return the client for the newly created storage directly.
            # It was just created, no need to refetch it.
            return self._get_resource_client(id=metadata.id), self._get_metadata(raw_metadata)

    @abstractmethod
    def _get_resource_client(self, id: str) -> TResourceClient:
        """Get a resource API client."""
