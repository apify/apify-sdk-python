from typing import TYPE_CHECKING, Dict, Optional, Type, TypeVar, Union, cast

from apify_client import ApifyClientAsync

from ..config import Configuration
from ..memory_storage import MemoryStorage

if TYPE_CHECKING:
    from .dataset import Dataset
    from .key_value_store import KeyValueStore
    from .request_queue import RequestQueue

T = TypeVar('T', 'Dataset', 'KeyValueStore', 'RequestQueue')


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
        store_id_or_name: Optional[str],
        client: Optional[Union[ApifyClientAsync, MemoryStorage]] = None,
        config: Optional[Configuration] = None,
    ) -> T:
        """TODO: docs."""
        storage_manager = StorageManager._get_default_instance()
        if storage_class not in storage_manager._cache:
            storage_manager._cache[storage_class] = {}
        if store_id_or_name is not None:
            storage = storage_manager._cache[storage_class].get(store_id_or_name, None)
            if storage:
                return cast(T, storage)  # TODO: This cast is a bit nasty, discuss a solution

        used_config = config or storage_manager._config
        storage = await storage_class.open(store_id_or_name, client or used_config.storage_client_manager.get_storage_client(), used_config)

        storage_manager._cache[storage_class][storage._id] = storage
        if storage._name is not None:
            storage_manager._cache[storage_class][storage._name] = storage  # TODO: Is this ok?
        return storage

    @classmethod
    async def close_storage(cls, storage_class: Type[Union['Dataset', 'KeyValueStore', 'RequestQueue']], id: str, name: Optional[str]) -> None:
        """TODO: docs."""
        storage_manager = StorageManager._get_default_instance()
        del storage_manager._cache[storage_class][id]
        if name is not None:
            del storage_manager._cache[storage_class][name]
