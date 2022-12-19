from operator import itemgetter
from typing import TYPE_CHECKING, Any, Dict, Optional

from ..._utils import ListPage
from ..file_storage_utils import update_metadata
from .key_value_store import KeyValueStoreClient, find_or_cache_key_value_store_by_possible_id

if TYPE_CHECKING:
    from ..memory_storage import MemoryStorage


class KeyValueStoreCollectionClient:

    def __init__(self, *, base_storage_directory: str, client: 'MemoryStorage') -> None:
        self.key_value_stores_directory = base_storage_directory
        self.client = client

    def list(self) -> ListPage:
        def map_store(store: KeyValueStoreClient) -> Dict:
            return store.to_key_value_store_info()
        return ListPage({
            'total': len(self.client.key_value_stores_handled),
            'count': len(self.client.key_value_stores_handled),
            'offset': 0,
            'limit': len(self.client.key_value_stores_handled),
            'desc': False,
            'items': sorted(map(map_store, self.client.key_value_stores_handled), key=itemgetter('createdAt')),
        })

    async def get_or_create(self, *, name: Optional[str] = None, schema: Optional[Dict] = None) -> Dict:
        if name:
            found = find_or_cache_key_value_store_by_possible_id(client=self.client, entry_name_or_id=name)

            if found:
                return found.to_key_value_store_info()

        new_store = KeyValueStoreClient(name=name, base_storage_directory=self.key_value_stores_directory, client=self.client)
        self.client.key_value_stores_handled.append(new_store)

        kv_store_info = new_store.to_key_value_store_info()

        # Write to the disk
        await update_metadata(data=kv_store_info, entity_directory=new_store.key_value_store_directory, write_metadata=self.client.write_metadata)

        return kv_store_info
