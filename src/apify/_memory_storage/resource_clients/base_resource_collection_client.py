from abc import ABC, abstractmethod
from operator import itemgetter
from typing import TYPE_CHECKING, Dict, Generic, List, Optional, Type, TypeVar

from apify_client._utils import ListPage

from ..._utils import ignore_docs
from ..file_storage_utils import _update_metadata
from .base_resource_client import BaseResourceClient

if TYPE_CHECKING:
    from ..memory_storage_client import MemoryStorageClient


ResourceClientType = TypeVar('ResourceClientType', bound=BaseResourceClient, contravariant=True)


@ignore_docs
class BaseResourceCollectionClient(ABC, Generic[ResourceClientType]):
    """Base class for resource collection clients."""

    _base_storage_directory: str
    _memory_storage_client: 'MemoryStorageClient'

    def __init__(self, *, base_storage_directory: str, memory_storage_client: 'MemoryStorageClient') -> None:
        """Initialize the DatasetCollectionClient with the passed arguments."""
        self._base_storage_directory = base_storage_directory
        self._memory_storage_client = memory_storage_client

    @abstractmethod
    def _get_storage_client_cache(self) -> List[ResourceClientType]:
        raise NotImplementedError('You must override this method in the subclass!')

    @abstractmethod
    def _get_resource_client_class(self) -> Type[ResourceClientType]:
        raise NotImplementedError('You must override this method in the subclass!')

    @abstractmethod
    async def list(self) -> ListPage:
        """List the available storages.

        Returns:
            ListPage: The list of available storages matching the specified filters.
        """
        storage_client_cache = self._get_storage_client_cache()

        items = [storage._to_resource_info() for storage in storage_client_cache]

        return ListPage({
            'total': len(items),
            'count': len(items),
            'offset': 0,
            'limit': len(items),
            'desc': False,
            'items': sorted(items, key=itemgetter('createdAt')),
        })

    @abstractmethod
    async def get_or_create(
        self,
        *,
        name: Optional[str] = None,
        schema: Optional[Dict] = None,  # noqa: U100
        _id: Optional[str] = None,
    ) -> Dict:
        """Retrieve a named storage, or create a new one when it doesn't exist.

        Args:
            name (str, optional): The name of the storage to retrieve or create.
            schema (Dict, optional): The schema of the storage

        Returns:
            dict: The retrieved or newly-created storage.
        """
        resource_client_class = self._get_resource_client_class()
        storage_client_cache = self._get_storage_client_cache()

        if name or _id:
            found = resource_client_class._find_or_create_client_by_id_or_name(memory_storage_client=self._memory_storage_client, name=name, id=_id)
            if found:
                return found._to_resource_info()

        new_resource = resource_client_class(
            id=_id,
            name=name,
            base_storage_directory=self._base_storage_directory,
            memory_storage_client=self._memory_storage_client,
        )
        storage_client_cache.append(new_resource)

        resource_info = new_resource._to_resource_info()

        # Write to the disk
        await _update_metadata(
            data=resource_info,
            entity_directory=new_resource._resource_directory,
            write_metadata=self._memory_storage_client._write_metadata,
        )

        return resource_info
