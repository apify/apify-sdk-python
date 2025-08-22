import asyncio

from typing_extensions import override

from crawlee.storages import RequestQueue

from apify.storage_clients._apify._request_queue_client import ApifyRequestQueueClient, ApifyRequestQueueMetadata


class ApifyRequestQueue(RequestQueue):
    @override
    def __init__(self, client: ApifyRequestQueueClient, id: str, name: str | None) -> None:
        """Initialize a new instance.

        Preferably use the `RequestQueue.open` constructor to create a new instance.

        Args:
            client: An instance of a storage client.
            id: The unique identifier of the storage.
            name: The name of the storage, if available.
        """
        self._client: ApifyRequestQueueClient = client
        self._id = id
        self._name = name

        self._add_requests_tasks = list[asyncio.Task]()
        """A list of tasks for adding requests to the queue."""

    @override
    async def get_metadata(self) -> ApifyRequestQueueMetadata:
        return await self._client.get_metadata()
