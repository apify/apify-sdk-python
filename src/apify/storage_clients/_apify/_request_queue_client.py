from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING, Final, Literal

from typing_extensions import override

from crawlee.storage_clients._base import RequestQueueClient

from ._api_client_creation import create_storage_api_client
from ._models import ApifyRequestQueueMetadata, RequestQueueStats
from ._request_queue_shared_client import ApifyRequestQueueSharedClient
from ._request_queue_single_client import ApifyRequestQueueSingleClient

if TYPE_CHECKING:
    from collections.abc import Sequence

    from apify_client.clients import RequestQueueClientAsync
    from crawlee import Request
    from crawlee.storage_clients.models import AddRequestsResponse, ProcessedRequest, RequestQueueMetadata

    from apify import Configuration

logger = getLogger(__name__)


class ApifyRequestQueueClient(RequestQueueClient):
    """Request queue client for the Apify platform.

    This client provides access to request queues stored on the Apify platform, supporting both single-consumer
    and multi-consumer scenarios. It manages local caching, request fetching, and state synchronization with the
    platform's API.
    """

    _MAX_CACHED_REQUESTS: Final[int] = 1_000_000
    """Maximum number of requests that can be cached locally."""

    def __init__(
        self,
        *,
        api_client: RequestQueueClientAsync,
        metadata: RequestQueueMetadata,
        access: Literal['single', 'shared'] = 'single',
    ) -> None:
        """Initialize a new instance.

        Preferably use the `ApifyRequestQueueClient.open` class method to create a new instance.
        """
        self._api_client = api_client
        """The Apify request queue client for API operations."""

        self._implementation: ApifyRequestQueueSingleClient | ApifyRequestQueueSharedClient
        """Internal implementation used to communicate with the Apify platform based request queue."""

        if access == 'single':
            self._implementation = ApifyRequestQueueSingleClient(
                api_client=self._api_client, metadata=metadata, cache_size=self._MAX_CACHED_REQUESTS
            )
        elif access == 'shared':
            self._implementation = ApifyRequestQueueSharedClient(
                api_client=self._api_client,
                metadata=metadata,
                cache_size=self._MAX_CACHED_REQUESTS,
                metadata_getter=self.get_metadata,
            )
        else:
            raise RuntimeError(f"Unsupported access type: {access}. Allowed values are 'single' or 'shared'.")

    @override
    async def get_metadata(self) -> ApifyRequestQueueMetadata:
        """Retrieve current metadata about the request queue.

        This method fetches metadata from the Apify API and merges it with local estimations to provide
        the most up-to-date statistics. Local estimations are used to compensate for potential delays
        in API data propagation (typically a few seconds).

        Returns:
            Request queue metadata with accurate counts and timestamps, combining API data with local estimates.
        """
        response = await self._api_client.get()

        if response is None:
            raise ValueError('Failed to fetch request queue metadata from the API.')

        # Enhance API response with local estimations to account for propagation delays (API data can be delayed
        # by a few seconds, while local estimates are immediately accurate).
        return ApifyRequestQueueMetadata(
            id=response['id'],
            name=response['name'],
            total_request_count=max(response['totalRequestCount'], self._implementation.metadata.total_request_count),
            handled_request_count=max(
                response['handledRequestCount'], self._implementation.metadata.handled_request_count
            ),
            pending_request_count=response['pendingRequestCount'],
            created_at=min(response['createdAt'], self._implementation.metadata.created_at),
            modified_at=max(response['modifiedAt'], self._implementation.metadata.modified_at),
            accessed_at=max(response['accessedAt'], self._implementation.metadata.accessed_at),
            had_multiple_clients=response['hadMultipleClients'] or self._implementation.metadata.had_multiple_clients,
            stats=RequestQueueStats.model_validate(response['stats'], by_alias=True),
        )

    @classmethod
    async def open(
        cls,
        *,
        id: str | None,
        name: str | None,
        alias: str | None,
        configuration: Configuration,
        access: Literal['single', 'shared'] = 'single',
    ) -> ApifyRequestQueueClient:
        """Open an Apify request queue client.

        This method creates and initializes a new request queue client instance, handling authentication,
        storage lookup or creation, metadata retrieval, and initialization of internal caching structures.

        Args:
            id: ID of an existing request queue to open. Mutually exclusive with `name` and `alias`.
            name: Name of the request queue to open or create (persists across Actor runs).
                Mutually exclusive with `id` and `alias`.
            alias: Alias for the request queue (scoped to current Actor run, creates unnamed storage).
                Mutually exclusive with `id` and `name`.
            configuration: Configuration object containing API credentials (`token`, `api_base_url`) and
                optionally a `default_request_queue_id` for fallback when no identifier is provided.
            access: Access mode controlling the client's behavior:
                - `single`: Optimized for single-consumer scenarios (lower API usage, better performance).
                - `shared`: Optimized for multi-consumer scenarios (more API calls, guaranteed consistency).

        Returns:
            An instance for the opened or created storage client.

        Raises:
            ValueError: If the configuration is missing required fields, if multiple identifiers (`id`, `name`,
                `alias`) are provided simultaneously, or if no identifier is provided and no default is configured.
        """
        api_client = await create_storage_api_client(
            storage_type='RequestQueue',
            configuration=configuration,
            alias=alias,
            name=name,
            id=id,
        )

        # Fetch initial metadata from the API.
        raw_metadata = await api_client.get()
        if raw_metadata is None:
            raise ValueError('Failed to retrieve request queue metadata from the API.')
        metadata = ApifyRequestQueueMetadata.model_validate(raw_metadata)

        return cls(
            api_client=api_client,
            metadata=metadata,
            access=access,
        )

    @override
    async def purge(self) -> None:
        raise NotImplementedError(
            'Purging the request queue is not supported in the Apify platform. '
            'Use the `drop` method to delete the request queue instead.'
        )

    @override
    async def drop(self) -> None:
        await self._api_client.delete()

    @override
    async def add_batch_of_requests(
        self,
        requests: Sequence[Request],
        *,
        forefront: bool = False,
    ) -> AddRequestsResponse:
        return await self._implementation.add_batch_of_requests(requests, forefront=forefront)

    @override
    async def fetch_next_request(self) -> Request | None:
        return await self._implementation.fetch_next_request()

    @override
    async def mark_request_as_handled(self, request: Request) -> ProcessedRequest | None:
        return await self._implementation.mark_request_as_handled(request)

    @override
    async def get_request(self, unique_key: str) -> Request | None:
        return await self._implementation.get_request(unique_key)

    @override
    async def reclaim_request(
        self,
        request: Request,
        *,
        forefront: bool = False,
    ) -> ProcessedRequest | None:
        return await self._implementation.reclaim_request(request, forefront=forefront)

    @override
    async def is_empty(self) -> bool:
        return await self._implementation.is_empty()
