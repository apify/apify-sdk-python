from typing import Dict, List, Optional, Type

from apify_client._utils import ListPage

from ..._utils import ignore_docs
from .base_resource_collection_client import BaseResourceCollectionClient
from .request_queue import RequestQueueClient


@ignore_docs
class RequestQueueCollectionClient(BaseResourceCollectionClient):
    """Sub-client for manipulating request queues."""

    def _get_storage_client_cache(self) -> List[RequestQueueClient]:
        return self._memory_storage_client._request_queues_handled

    def _get_resource_client_class(self) -> Type[RequestQueueClient]:
        return RequestQueueClient

    async def list(self) -> ListPage:
        """List the available request queues.

        Returns:
            ListPage: The list of available request queues matching the specified filters.
        """
        return await super().list()

    async def get_or_create(
        self,
        *,
        name: Optional[str] = None,
        schema: Optional[Dict] = None,
        _id: Optional[str] = None,
    ) -> Dict:
        """Retrieve a named request queue, or create a new one when it doesn't exist.

        Args:
            name (str, optional): The name of the request queue to retrieve or create.
            schema (Dict, optional): The schema of the request queue

        Returns:
            dict: The retrieved or newly-created request queue.
        """
        return await super().get_or_create(name=name, schema=schema, _id=_id)
