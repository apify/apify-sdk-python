import json
import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional

from typing_extensions import Self

if TYPE_CHECKING:
    from ..memory_storage import MemoryStorage


class BaseResourceClient(ABC):
    """Base class for resource clients."""

    _id: str
    _name: Optional[str]

    @classmethod
    @abstractmethod
    def _get_storages_dir(cls, memory_storage: 'MemoryStorage') -> str:
        raise NotImplementedError('You must override this method in the subclass!')

    @classmethod
    @abstractmethod
    def _get_storage_client_cache(cls, memory_storage: 'MemoryStorage') -> List[Self]:
        raise NotImplementedError('You must override this method in the subclass!')

    @classmethod
    @abstractmethod
    def _create_from_directory(
        cls,
        storage_directory: str,
        memory_storage: 'MemoryStorage',
        id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Self:
        raise NotImplementedError('You must override this method in the subclass!')

    @classmethod
    def _find_or_create_client_by_id_or_name(
        cls,
        memory_storage: 'MemoryStorage',
        id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Optional[Self]:
        name_or_id = name or id
        assert name_or_id is not None

        storage_client_cache = cls._get_storage_client_cache(memory_storage)
        storages_dir = cls._get_storages_dir(memory_storage)

        # First check memory cache
        found = next((storage_client for storage_client in storage_client_cache
                      if storage_client._id == id or (storage_client._name and name and storage_client._name.lower() == name.lower())), None)

        if found is not None:
            return found

        storage_path = None
        # First try to find the storage by looking up the directory by name
        if name:
            possible_storage_path = os.path.join(storages_dir, name)
            if os.access(possible_storage_path, os.F_OK):
                storage_path = possible_storage_path

        # If it's not found, try going throuth the storages dir and finding it by metadata
        if not storage_path:
            if os.access(storages_dir, os.F_OK):
                for entry in os.scandir(storages_dir):
                    if not entry.is_dir():
                        continue
                    metadata_path = os.path.join(entry.path, '__metadata__.json')
                    if not os.access(metadata_path, os.F_OK):
                        continue
                    with open(metadata_path) as metadata_file:
                        metadata = json.load(metadata_file)
                    if id and id == metadata.get('id'):
                        storage_path = entry.path
                        name = metadata.get(name)
                        break
                    if name and name == metadata.get('name'):
                        storage_path = entry.path
                        id = metadata.get(id)
                        break

        if not storage_path:
            return None

        resource_client = cls._create_from_directory(storage_path, memory_storage, id, name)

        storage_client_cache.append(resource_client)

        return resource_client
