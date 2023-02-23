from operator import itemgetter
from typing import TYPE_CHECKING, Dict, Optional

from apify_client._utils import ListPage

from ..file_storage_utils import _update_metadata
from .dataset import DatasetClient

if TYPE_CHECKING:
    from ..memory_storage import MemoryStorage


class DatasetCollectionClient:
    """Sub-client for manipulating datasets."""

    _datasets_directory: str
    _memory_storage: 'MemoryStorage'

    def __init__(self, *, base_storage_directory: str, memory_storage: 'MemoryStorage') -> None:
        """Initialize the DatasetCollectionClient with the passed arguments."""
        self._datasets_directory = base_storage_directory
        self._memory_storage = memory_storage

    def list(self) -> ListPage:
        """List the available datasets.

        Returns:
            ListPage: The list of available datasets matching the specified filters.
        """
        def map_store(store: DatasetClient) -> Dict:
            return store._to_dataset_info()
        return ListPage({
            'total': len(self._memory_storage._datasets_handled),
            'count': len(self._memory_storage._datasets_handled),
            'offset': 0,
            'limit': len(self._memory_storage._datasets_handled),
            'desc': False,
            'items': sorted(map(map_store, self._memory_storage._datasets_handled), key=itemgetter('createdAt')),
        })

    async def get_or_create(self, *, name: Optional[str] = None, _schema: Optional[Dict] = None) -> Dict:
        """Retrieve a named dataset, or create a new one when it doesn't exist.

        Args:
            name (str, optional): The name of the dataset to retrieve or create.
            schema (Dict, optional): The schema of the dataset

        Returns:
            dict: The retrieved or newly-created dataset.
        """
        if name:
            found = DatasetClient._find_or_create_client_by_id_or_name(memory_storage=self._memory_storage, name=name)

            if found:
                return found._to_dataset_info()

        new_dataset = DatasetClient(name=name, base_storage_directory=self._datasets_directory, memory_storage=self._memory_storage)
        self._memory_storage._datasets_handled.append(new_dataset)

        dataset_info = new_dataset._to_dataset_info()

        # Write to the disk
        await _update_metadata(
            data=dataset_info,
            entity_directory=new_dataset._dataset_directory,
            write_metadata=self._memory_storage._write_metadata,
        )

        return dataset_info
