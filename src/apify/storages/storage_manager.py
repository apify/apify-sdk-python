from typing import TYPE_CHECKING, Dict, Optional, Protocol, Type, TypeVar, Union, cast

from apify_client import ApifyClientAsync

from ..config import Configuration
from ..memory_storage import MemoryStorage
from ..storage_client_manager import StorageClientManager

if TYPE_CHECKING:
    from .dataset import Dataset
    from .key_value_store import KeyValueStore
    from .request_queue import RequestQueue

T = TypeVar('T', 'Dataset', 'KeyValueStore', 'RequestQueue', covariant=True)


class Storage(Protocol[T]):
    """A protocol defining common interface for storage classes."""

    @classmethod
    def _create_instance(cls, storage_id_or_name: str, client: Union[ApifyClientAsync, MemoryStorage]) -> T:
        ...

    @classmethod
    def _get_default_name(cls, config: Configuration) -> str:
        ...


async def _purge_default_storages(client: Union[ApifyClientAsync, MemoryStorage]) -> None:
    if isinstance(client, MemoryStorage) and not client._purged:
        client._purged = True
        await client.purge()


class StorageManager:
    """A class for managing storages."""

    _default_instance: Optional['StorageManager'] = None
    _cache: Dict[Type[Storage], Dict[str, Storage]]

    def __init__(self) -> None:
        """Create a `StorageManager` instance."""
        self._cache = {}

    @classmethod
    def _get_default_instance(cls) -> 'StorageManager':
        if cls._default_instance is None:
            cls._default_instance = cls()

        return cls._default_instance

    @classmethod
    async def open_storage(
        cls,
        storage_class: Type[T],
        storage_id_or_name: Optional[str] = None,
        client: Optional[Union[ApifyClientAsync, MemoryStorage]] = None,
        config: Optional[Configuration] = None,
    ) -> T:
        """Open a storage of the given class, or return a cached storage object if it was opened before.

        Opens a new storage (`Dataset`, `KeyValueStore`, or `RequestQueue`) with the given ID or name.
        Returns the cached storage object if the storage was opened before.

        Args:
            storage_class (Type[Dataset] or Type[KeyValueStore] or Type[RequestQueue]): Class of the storage to be opened.
            storage_id_or_name (str, optional): ID or name of the storage to be opened. If omitted, an unnamed storage will be opened.
            client (ApifyClientAsync or MemoryStorage, optional): The storage client which should be used in the storage.
                If omitted, the default client will be used.
            config (Configuration, optional): The actor configuration to be used in this call. If omitted, the global configuration will be used.

        Returns:
            An instance of the storage given by `storage_class`.
        """
        storage_manager = StorageManager._get_default_instance()
        used_config = config or Configuration.get_global_configuration()
        used_client = client or StorageClientManager.get_storage_client()

        # Create cache for the given storage class if missing
        if storage_class not in storage_manager._cache:
            storage_manager._cache[storage_class] = {}

        # Fetch default name
        if not storage_id_or_name:
            storage_id_or_name = storage_class._get_default_name(used_config)

        # Try to get the storage instance from cache
        storage = storage_manager._cache[storage_class].get(storage_id_or_name, None)
        if storage is not None:
            # This cast is needed since we're storing all storages in one union dictionary
            return cast(T, storage)

        # Purge default storages if configured
        if used_config.purge_on_start:
            await _purge_default_storages(used_client)

        # Create the storage
        storage = await storage_class._create_instance(storage_id_or_name, used_client)

        # Cache by id and name
        storage_manager._cache[storage_class][storage._id] = storage
        if storage._name is not None:
            storage_manager._cache[storage_class][storage._name] = storage
        return storage

    @classmethod
    async def close_storage(cls, storage_class: Type[Storage], id: str, name: Optional[str]) -> None:
        """Close the given storage by removing it from the cache.

        Args:
            storage_class (Type[Dataset] or Type[KeyValueStore] or Type[RequestQueue]): Class of the storage to be closed.
            id (str): ID of the storage to be closed.
            name (str, optional): Name of the storage to be closed.
        """
        storage_manager = StorageManager._get_default_instance()
        del storage_manager._cache[storage_class][id]
        if name is not None:
            del storage_manager._cache[storage_class][name]
