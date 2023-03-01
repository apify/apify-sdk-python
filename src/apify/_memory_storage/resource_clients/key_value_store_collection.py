from typing import Dict, List, Optional, Type

from apify_client._utils import ListPage

from ..._utils import ignore_docs
from .base_resource_collection_client import BaseResourceCollectionClient
from .key_value_store import KeyValueStoreClient


@ignore_docs
class KeyValueStoreCollectionClient(BaseResourceCollectionClient):
    """Sub-client for manipulating key-value stores."""

    def _get_storage_client_cache(self) -> List[KeyValueStoreClient]:
        return self._memory_storage_client._key_value_stores_handled

    def _get_resource_client_class(self) -> Type[KeyValueStoreClient]:
        return KeyValueStoreClient

    async def list(self) -> ListPage:
        """List the available key-value stores.

        Returns:
            ListPage: The list of available key-value stores matching the specified filters.
        """
        return await super().list()

    async def get_or_create(
        self,
        *,
        name: Optional[str] = None,
        schema: Optional[Dict] = None,
        _id: Optional[str] = None,
    ) -> Dict:
        """Retrieve a named key-value store, or create a new one when it doesn't exist.

        Args:
            name (str, optional): The name of the key-value store to retrieve or create.
            schema (Dict, optional): The schema of the key-value store

        Returns:
            dict: The retrieved or newly-created key-value store.
        """
        return await super().get_or_create(name=name, schema=schema, _id=_id)
