from operator import itemgetter
from typing import TYPE_CHECKING, Dict, Optional

from ..._utils import ListPage
from ..file_storage_utils import _update_metadata
from .dataset import DatasetClient, _find_or_cache_dataset_by_possible_id

if TYPE_CHECKING:
    from ..memory_storage import MemoryStorage


class DatasetCollectionClient:
    """TODO: docs."""

    def __init__(self, *, base_storage_directory: str, client: 'MemoryStorage') -> None:
        """TODO: docs."""
        self.datasets_directory = base_storage_directory
        self.client = client

    def list(self) -> ListPage:
        """TODO: docs."""
        def map_store(store: DatasetClient) -> Dict:
            return store.to_dataset_info()
        return ListPage({
            'total': len(self.client.datasets_handled),
            'count': len(self.client.datasets_handled),
            'offset': 0,
            'limit': len(self.client.datasets_handled),
            'desc': False,
            'items': sorted(map(map_store, self.client.datasets_handled), key=itemgetter('createdAt')),
        })

    async def get_or_create(self, *, name: Optional[str] = None, schema: Optional[Dict] = None) -> Dict:
        """TODO: docs."""
        if name:
            found = _find_or_cache_dataset_by_possible_id(client=self.client, entry_name_or_id=name)

            if found:
                return found.to_dataset_info()

        new_store = DatasetClient(name=name, base_storage_directory=self.datasets_directory, client=self.client)
        self.client.datasets_handled.append(new_store)

        dataset_info = new_store.to_dataset_info()

        # Write to the disk
        await _update_metadata(data=dataset_info, entity_directory=new_store.dataset_directory, write_metadata=self.client.write_metadata)

        return dataset_info
