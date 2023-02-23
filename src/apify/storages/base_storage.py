from abc import ABC, abstractmethod
from typing import Dict, Optional, Protocol, Union, cast

from typing_extensions import Self

from apify_client import ApifyClientAsync

from ..config import Configuration
from ..memory_storage import MemoryStorage
from .storage_client_manager import StorageClientManager


class _SingleStorageClientProtocol(Protocol):
    async def get(self) -> Optional[Dict]:
        pass


class _StorageCollectionClientProtocol(Protocol):
    async def get_or_create(self, *, name: Optional[str] = None) -> Dict:
        pass


async def _purge_default_storages(client: Union[ApifyClientAsync, MemoryStorage]) -> None:
    if isinstance(client, MemoryStorage) and not client._purged:
        client._purged = True
        await client.purge()


class BaseStorage(ABC):
    """A class for managing storages."""

    _id: str
    _name: Optional[str]
    _storage_client: Union[ApifyClientAsync, MemoryStorage]

    _cache_by_id: Optional[Dict[str, Self]] = None
    _cache_by_name: Optional[Dict[str, Self]] = None

    def __init__(self, id: str, name: Optional[str], client: Union[ApifyClientAsync, MemoryStorage]):
        """Initialize the storage.

        Do not use this method directly, but use `Actor.open_<STORAGE>()` instead.

        Args:
            id (str): The storage id
            name (str, optional): The storage name
            client (ApifyClientAsync or MemoryStorage): The storage client
        """
        self._id = id
        self._name = name
        self._storage_client = client

    @classmethod
    @abstractmethod
    def _get_human_friendly_label(cls) -> str:
        raise NotImplementedError('You must override this method in the subclass!')

    @classmethod
    @abstractmethod
    def _get_default_id(cls, config: Configuration) -> str:
        raise NotImplementedError('You must override this method in the subclass!')

    @classmethod
    @abstractmethod
    def _get_single_storage_client(cls, id: str, client: Union[ApifyClientAsync, MemoryStorage]) -> _SingleStorageClientProtocol:
        raise NotImplementedError('You must override this method in the subclass!')

    @classmethod
    @abstractmethod
    def _get_storage_collection_client(cls, client: Union[ApifyClientAsync, MemoryStorage]) -> _StorageCollectionClientProtocol:
        raise NotImplementedError('You must override this method in the subclass!')

    @classmethod
    def _ensure_caches_initialized(cls) -> None:
        if cls._cache_by_id is None:
            cls._cache_by_id = {}
        if cls._cache_by_name is None:
            cls._cache_by_name = {}

    @classmethod
    async def open(
        cls,
        *,
        id: Optional[str] = None,
        name: Optional[str] = None,
        force_cloud: bool = False,
        config: Optional[Configuration] = None,
    ) -> Self:
        """Open a storage, or return a cached storage object if it was opened before.

        Opens a storage with the given ID or name.
        Returns the cached storage object if the storage was opened before.

        Args:
            id (str, optional): ID of the storage to be opened.
                If neither `id` nor `name` are provided, the method returns the default storage associated with the actor run.
                If the storage with the given ID does not exist, it raises an error.
            name (str, optional): Name of the storage to be opened.
                If neither `id` nor `name` are provided, the method returns the default storage associated with the actor run.
                If the storage with the given name does not exist, it is created.
            force_cloud (bool, optional): If set to True, it will open a storage on the Apify Platform even when running the actor locally.
                Defaults to False.
            config (Configuration, optional): A `Configuration` instance, uses global configuration if omitted.

        Returns:
            An instance of the storage given by `storage_class`.
        """
        cls._ensure_caches_initialized()
        assert cls._cache_by_id is not None
        assert cls._cache_by_name is not None

        assert not (id and name)

        used_config = config or Configuration.get_global_configuration()
        used_client = StorageClientManager.get_storage_client(force_cloud=force_cloud)

        # Fetch default name
        if not id and not name:
            default_id = cls._get_default_id(used_config)
            if isinstance(used_client, ApifyClientAsync):
                id = default_id
            else:
                name = default_id

        # Try to get the storage instance from cache
        cached_storage = None
        if id:
            cached_storage = cls._cache_by_id.get(id)
        elif name:
            cached_storage = cls._cache_by_name.get(name)

        if cached_storage is not None:
            # This cast is needed since MyPy doesn't understand very well that Self and Storage are the same
            return cast(Self, cached_storage)

        # Purge default storages if configured
        if used_config.purge_on_start:
            await _purge_default_storages(used_client)

        # Create the storage
        if id:
            single_storage_client = cls._get_single_storage_client(id, used_client)
            storage_info = await single_storage_client.get()
            if not storage_info:
                storage_label = cls._get_human_friendly_label()
                raise RuntimeError(f'{storage_label} with id "{id}" does not exist!')
        else:
            storage_collection_client = cls._get_storage_collection_client(used_client)
            storage_info = await storage_collection_client.get_or_create(name=name)

        storage = cls(storage_info['id'], storage_info.get('name'), used_client)

        # Cache by id and name
        cls._cache_by_id[storage._id] = storage
        if storage._name is not None:
            cls._cache_by_name[storage._name] = storage
        return storage

    async def _remove_from_cache(self) -> None:
        if self.__class__._cache_by_id is not None:
            del self.__class__._cache_by_id[self._id]
            if self.__class__._cache_by_name is not None:
                if self._name is not None:
                    del self.__class__._cache_by_name[self._name]
