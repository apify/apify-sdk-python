from typing import TYPE_CHECKING, Dict, Optional, Type, TypeVar, Union, cast

from apify_client import ApifyClientAsync

from ..config import Configuration
from ..memory_storage import MemoryStorage
from ..storage_client_manager import StorageClientManager

if TYPE_CHECKING:
    from .dataset import Dataset
    from .key_value_store import KeyValueStore
    from .request_queue import RequestQueue

T = TypeVar('T', 'Dataset', 'KeyValueStore', 'RequestQueue')


async def _purge_default_storages(client: Union[ApifyClientAsync, MemoryStorage]) -> None:
    if isinstance(client, MemoryStorage) and not client._purged:
        client._purged = True
        await client.purge()


class StorageManager:
    """TODO: docs."""

    _default_instance: Optional['StorageManager'] = None
    _cache: Dict[Type[Union['Dataset', 'KeyValueStore', 'RequestQueue']], Dict[str, Union['Dataset', 'KeyValueStore', 'RequestQueue']]]
    _config: Configuration

    def __init__(self) -> None:
        """TODO: docs."""
        self._cache = {}
        self._config = Configuration.get_global_configuration()

    @classmethod
    def _get_default_instance(cls) -> 'StorageManager':
        if cls._default_instance is None:
            cls._default_instance = cls()

        return cls._default_instance

    @classmethod
    async def open_storage(
        cls,
        storage_class: Type[T],
        store_id_or_name: Optional[str] = None,
        client: Optional[Union[ApifyClientAsync, MemoryStorage]] = None,
        config: Optional[Configuration] = None,
    ) -> T:
        """TODO: docs."""
        storage_manager = StorageManager._get_default_instance()
        used_config = config or storage_manager._config
        used_client = client or StorageClientManager.get_storage_client()

        # Create cache for the given storage class if missing
        if storage_class not in storage_manager._cache:
            storage_manager._cache[storage_class] = {}

        # Fetch default name
        if not store_id_or_name:
            store_id_or_name = storage_class._get_default_name(used_config)

        # Try to get the storage instance from cache
        storage = storage_manager._cache[storage_class].get(store_id_or_name, None)
        if storage is not None:
            # This cast is needed since we're storing all storages in one union dictionary
            return cast(T, storage)

        # Purge default storages if configured
        if used_config.purge_on_start:
            await _purge_default_storages(used_client)

        # Create the storage
        storage = await storage_class._create_instance(store_id_or_name, used_client)

        # Cache by id and name
        storage_manager._cache[storage_class][storage._id] = storage
        if storage._name is not None:
            storage_manager._cache[storage_class][storage._name] = storage
        return storage

    @classmethod
    async def close_storage(cls, storage_class: Type[Union['Dataset', 'KeyValueStore', 'RequestQueue']], id: str, name: Optional[str]) -> None:
        """TODO: docs."""
        storage_manager = StorageManager._get_default_instance()
        del storage_manager._cache[storage_class][id]
        if name is not None:
            del storage_manager._cache[storage_class][name]
