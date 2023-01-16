from operator import itemgetter
from typing import TYPE_CHECKING, Dict, Optional

from apify_client._utils import ListPage

from ..file_storage_utils import _update_metadata
from .request_queue import RequestQueueClient, _find_or_cache_request_queue_by_possible_id

if TYPE_CHECKING:
    from ..memory_storage import MemoryStorage


class RequestQueueCollectionClient:
    """TODO: docs."""

    _request_queues_directory: str
    _client: 'MemoryStorage'

    def __init__(self, *, base_storage_directory: str, client: 'MemoryStorage') -> None:
        """TODO: docs."""
        self._request_queues_directory = base_storage_directory
        self._client = client

    def list(self) -> ListPage:
        """TODO: docs."""
        def map_store(store: RequestQueueClient) -> Dict:
            return store.to_request_queue_info()
        return ListPage({
            'total': len(self._client._request_queues_handled),
            'count': len(self._client._request_queues_handled),
            'offset': 0,
            'limit': len(self._client._request_queues_handled),
            'desc': False,
            'items': sorted(map(map_store, self._client._request_queues_handled), key=itemgetter('createdAt')),
        })

    async def get_or_create(self, *, name: Optional[str] = None) -> Dict:
        """TODO: docs."""
        if name:
            found = _find_or_cache_request_queue_by_possible_id(self._client, name)

            if found:
                return found.to_request_queue_info()

        new_queue = RequestQueueClient(name=name, base_storage_directory=self._request_queues_directory, client=self._client)
        self._client._request_queues_handled.append(new_queue)

        request_queue_info = new_queue.to_request_queue_info()

        # Write to the disk
        await _update_metadata(
            data=request_queue_info,
            entity_directory=new_queue._request_queue_directory,
            write_metadata=self._client._write_metadata,
        )

        return request_queue_info
