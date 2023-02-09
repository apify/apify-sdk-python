from operator import itemgetter
from typing import TYPE_CHECKING, Dict, Optional

from apify_client._utils import ListPage

from ..file_storage_utils import _update_metadata
from .key_value_store import KeyValueStoreClient, _find_or_cache_key_value_store_by_possible_id

if TYPE_CHECKING:
    from ..memory_storage import MemoryStorage


class KeyValueStoreCollectionClient:
    """Sub-client for manipulating key-value stores."""

    _key_value_stores_directory: str
    _client: 'MemoryStorage'

    def __init__(self, *, base_storage_directory: str, client: 'MemoryStorage') -> None:
        """Initialize the KeyValueStoreCollectionClient with the passed arguments."""
        self._key_value_stores_directory = base_storage_directory
        self._client = client

    def list(self) -> ListPage:
        """List the available key-value stores.

        Returns:
            ListPage: The list of available key-value stores matching the specified filters.
        """
        def map_store(store: KeyValueStoreClient) -> Dict:
            return store.to_key_value_store_info()
        return ListPage({
            'total': len(self._client._key_value_stores_handled),
            'count': len(self._client._key_value_stores_handled),
            'offset': 0,
            'limit': len(self._client._key_value_stores_handled),
            'desc': False,
            'items': sorted(map(map_store, self._client._key_value_stores_handled), key=itemgetter('createdAt')),
        })

    async def get_or_create(self, *, name: Optional[str] = None, _schema: Optional[Dict] = None) -> Dict:
        """Retrieve a named key-value store, or create a new one when it doesn't exist.

        Args:
            name (str, optional): The name of the key-value store to retrieve or create.
            schema (Dict, optional): The schema of the key-value store

        Returns:
            dict: The retrieved or newly-created key-value store.
        """
        if name:
            found = _find_or_cache_key_value_store_by_possible_id(client=self._client, entry_name_or_id=name)

            if found:
                return found.to_key_value_store_info()

        new_store = KeyValueStoreClient(name=name, base_storage_directory=self._key_value_stores_directory, client=self._client)
        self._client._key_value_stores_handled.append(new_store)

        kv_store_info = new_store.to_key_value_store_info()

        # Write to the disk
        await _update_metadata(data=kv_store_info, entity_directory=new_store._key_value_store_directory, write_metadata=self._client._write_metadata)

        return kv_store_info
