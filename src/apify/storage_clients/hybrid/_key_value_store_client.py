from __future__ import annotations

import asyncio
from crawlee.events._types import Event, EventPersistStateData

from apify_client import ApifyClientAsync
from apify_client.clients import RequestQueueClientAsync
from crawlee import Request, service_locator
from crawlee.storage_clients._memory import MemoryRequestQueueClient
from crawlee.storage_clients.models import RequestQueueMetadata

from logging import getLogger

from src.apify._configuration import Configuration

logger = getLogger(__name__)

class HybridRequestQueueClient(MemoryRequestQueueClient):
    """RequestQueue implementation that uses `MemoryRequestQueueClient` with limited persistence capability.

    Advantages:
    - Fast in-memory operations.
    - Cheap RequestQueue as it uses platform RequestQueue only for persistence.

    Drawbacks:
    - Uses memory of the crawler.
    - Cannot be used with multiple consumers.
    - Migration is not guaranteed to work for large RequestQueue due to limited migration time window.

    Ideal use case:
    - Isolated crawlers with limited lifespan. (One RQ consumer, less than 10k requests)

    If the `HybridRequestQueueClient` is not sufficient for your use case, consider using request queue for adults
    `ApifyRequestQueueClient` instead.
    """
    def __init__(
        self,
        *,
        metadata: RequestQueueMetadata,
        api_client: RequestQueueClientAsync,
    ) -> None:
        super().__init__(metadata=metadata)
        logger.info(
            "Using `HybridRequestQueueClient`. Consider using `ApifyRequestQueueClient` for more complex crawlers.")

        self._api_client = api_client
        """The Apify request queue client for API operations."""

        # Register persistence listener
        event_manager = service_locator.get_event_manager()
        event_manager.on(event=Event.PERSIST_STATE, listener=self.to_apify_request_queue)

    @classmethod
    async def open(
        cls,
        *,
        id: str | None,
        name: str | None,
        configuration: Configuration,
    ) -> HybridRequestQueueClient:
        # COPYPASTA from ApifyRequestQueueClient.open TODO: Refactor if team agrees on this idea.
        token = configuration.token
        if not token:
            raise ValueError(f'Apify storage client requires a valid token in Configuration (token={token}).')

        api_url = configuration.api_base_url
        if not api_url:
            raise ValueError(f'Apify storage client requires a valid API URL in Configuration (api_url={api_url}).')

        api_public_base_url = configuration.api_public_base_url
        if not api_public_base_url:
            raise ValueError(
                'Apify storage client requires a valid API public base URL in Configuration '
                f'(api_public_base_url={api_public_base_url}).'
            )

        # Create Apify client with the provided token and API URL.
        apify_client_async = ApifyClientAsync(
            token=token,
            api_url=api_url,
            max_retries=8,
            min_delay_between_retries_millis=500,
            timeout_secs=360,
        )
        apify_rqs_client = apify_client_async.request_queues()

        # If both id and name are provided, raise an error.
        if id and name:
            raise ValueError('Only one of "id" or "name" can be specified, not both.')

        # If id is provided, get the storage by ID.
        if id and name is None:
            apify_rq_client = apify_client_async.request_queue(request_queue_id=id)

        # If name is provided, get or create the storage by name.
        if name and id is None:
            id = RequestQueueMetadata.model_validate(
                await apify_rqs_client.get_or_create(name=name),
            ).id
            apify_rq_client = apify_client_async.request_queue(request_queue_id=id)

        # If both id and name are None, try to get the default storage ID from environment variables.
        if id is None and name is None:
            id = configuration.default_request_queue_id
            apify_rq_client = apify_client_async.request_queue(request_queue_id=id)

        # Fetch its metadata.
        metadata = await apify_rq_client.get()

        # If metadata is None, it means the storage does not exist, so we create it.
        if metadata is None:
            id = RequestQueueMetadata.model_validate(
                await apify_rqs_client.get_or_create(),
            ).id
            apify_rq_client = apify_client_async.request_queue(request_queue_id=id)

        # Verify that the storage exists by fetching its metadata again.
        metadata = await apify_rq_client.get()
        if metadata is None:
            raise ValueError(f'Opening request queue with id={id} and name={name} failed.')

        local_rq = cls(
            metadata= RequestQueueMetadata.model_validate(await apify_rq_client.get()),
            api_client=apify_rq_client,
        )
        await local_rq.from_apify_request_queue()


    async def from_apify_request_queue(self)->HybridRequestQueueClient:
        """Should be called when after migration."""
        requests = []
        start = ""

        while True:
            raw_request_batch = (await self.apify_rq_client.list_requests(exclusive_start_id=start, limit=10000))["items"]
            for raw_request in raw_request_batch:
                if (request:=Request.model_validate(raw_request)).handled_at:
                    self._handled_requests[request.url]=request
                else:
                    self._pending_requests.append(request)
                self._requests_by_id[request.id]=request
                self._requests_by_unique_key[request.unique_key]=request


            if len(raw_request_batch) < 10000:
                break
            start = requests[-1].start

    async def to_apify_request_queue(self)->HybridRequestQueueClient:
        """Should be called before migration."""
        await self.apify_rq_client.batch_add_requests((request.model_dump(by_alias=True, exclude=["id"]) for request in self._pending_requests))
        await self.apify_rq_client.batch_add_requests((request.model_dump(by_alias=True, exclude=["id"]) for request in self._handled_requests.values()))


async def main():
    rq = await HybridRequestQueueClient.open()
    await rq.from_apify_request_queue()
    await rq.to_apify_request_queue()

if __name__ == "__main__":
    asyncio.run(main())

