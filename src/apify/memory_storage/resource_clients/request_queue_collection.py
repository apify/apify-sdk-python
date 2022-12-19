from operator import itemgetter
from typing import TYPE_CHECKING, Dict, Optional

from ..._utils import ListPage
from ..file_storage_utils import update_metadata
from .request_queue import RequestQueueClient, find_or_cache_request_queue_by_possible_id

if TYPE_CHECKING:
    from ..memory_storage import MemoryStorage


class RequestQueueCollectionClient:

    def __init__(self, *, base_storage_directory: str, client: 'MemoryStorage') -> None:
        self.request_queues_directory = base_storage_directory
        self.client = client

    def list(self) -> ListPage:
        def map_store(store: RequestQueueClient) -> Dict:
            return store.to_request_queue_info()
        return ListPage({
            'total': len(self.client.request_queues_handled),
            'count': len(self.client.request_queues_handled),
            'offset': 0,
            'limit': len(self.client.request_queues_handled),
            'desc': False,
            'items': sorted(map(map_store, self.client.request_queues_handled), key=itemgetter('createdAt')),
        })

    async def get_or_create(self, *, name: Optional[str] = None) -> Dict:
        if name:
            found = find_or_cache_request_queue_by_possible_id(self.client, name)

            if found:
                return found.to_request_queue_info()

        new_store = RequestQueueClient(name=name, base_storage_directory=self.request_queues_directory, client=self.client)
        self.client.request_queues_handled.append(new_store)

        request_queue_info = new_store.to_request_queue_info()

        # Write to the disk
        await update_metadata(data=request_queue_info, entity_directory=new_store.request_queue_directory, write_metadata=self.client.write_metadata)

        return request_queue_info
