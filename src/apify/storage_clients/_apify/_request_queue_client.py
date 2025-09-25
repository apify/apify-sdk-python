from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING, Final, Literal

from typing_extensions import override

from apify_client import ApifyClientAsync
from crawlee._utils.crypto import crypto_random_object_id
from crawlee.storage_clients._base import RequestQueueClient
from crawlee.storage_clients.models import AddRequestsResponse, ProcessedRequest, RequestQueueMetadata
from crawlee.storages import RequestQueue

from ._models import ApifyRequestQueueMetadata, RequestQueueStats
from ._request_queue_shared_client import _ApifyRequestQueueSharedClient
from ._request_queue_single_client import _ApifyRequestQueueSingleClient
from ._utils import AliasResolver

if TYPE_CHECKING:
    from collections.abc import Sequence

    from apify_client.clients import RequestQueueClientAsync
    from crawlee import Request

    from apify import Configuration

logger = getLogger(__name__)


class ApifyRequestQueueClient(RequestQueueClient):
    """Base class for Apify platform implementations of the request queue client."""

    _MAX_CACHED_REQUESTS: Final[int] = 1_000_000
    """Maximum number of requests that can be cached."""

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

        self._implementation: _ApifyRequestQueueSingleClient | _ApifyRequestQueueSharedClient
        """Internal implementation used to communicate with the Apify platform based Request Queue."""
        if access == 'single':
            self._implementation = _ApifyRequestQueueSingleClient(
                api_client=self._api_client, metadata=metadata, cache_size=self._MAX_CACHED_REQUESTS
            )
        elif access == 'shared':
            self._implementation = _ApifyRequestQueueSharedClient(
                api_client=self._api_client,
                metadata=metadata,
                cache_size=self._MAX_CACHED_REQUESTS,
                metadata_getter=self.get_metadata,
            )
        else:
            raise RuntimeError(f"Unsupported access type: {access}. Allowed values are 'single' or 'shared'.")

    @property
    def _metadata(self) -> RequestQueueMetadata:
        return self._implementation.metadata

    @override
    async def add_batch_of_requests(
        self,
        requests: Sequence[Request],
        *,
        forefront: bool = False,
    ) -> AddRequestsResponse:
        """Add a batch of requests to the queue.

        Args:
            requests: The requests to add.
            forefront: Whether to add the requests to the beginning of the queue.

        Returns:
            Response containing information about the added requests.
        """
        return await self._implementation.add_batch_of_requests(requests, forefront=forefront)

    @override
    async def fetch_next_request(self) -> Request | None:
        """Return the next request in the queue to be processed.

        Once you successfully finish processing of the request, you need to call `mark_request_as_handled`
        to mark the request as handled in the queue. If there was some error in processing the request, call
        `reclaim_request` instead, so that the queue will give the request to some other consumer
        in another call to the `fetch_next_request` method.

        Returns:
            The request or `None` if there are no more pending requests.
        """
        return await self._implementation.fetch_next_request()

    @override
    async def mark_request_as_handled(self, request: Request) -> ProcessedRequest | None:
        """Mark a request as handled after successful processing.

        Handled requests will never again be returned by the `fetch_next_request` method.

        Args:
            request: The request to mark as handled.

        Returns:
            Information about the queue operation. `None` if the given request was not in progress.
        """
        return await self._implementation.mark_request_as_handled(request)

    @override
    async def get_request(self, unique_key: str) -> Request | None:
        """Get a request by unique key.

        Args:
            unique_key: Unique key of the request to get.

        Returns:
            The request or None if not found.
        """
        return await self._implementation.get_request(unique_key)

    @override
    async def reclaim_request(
        self,
        request: Request,
        *,
        forefront: bool = False,
    ) -> ProcessedRequest | None:
        """Reclaim a failed request back to the queue.

        The request will be returned for processing later again by another call to `fetch_next_request`.

        Args:
            request: The request to return to the queue.
            forefront: Whether to add the request to the head or the end of the queue.

        Returns:
            Information about the queue operation. `None` if the given request was not in progress.
        """
        return await self._implementation.reclaim_request(request, forefront=forefront)

    @override
    async def is_empty(self) -> bool:
        """Check if the queue is empty.

        Returns:
            True if the queue is empty, False otherwise.
        """
        return await self._implementation.is_empty()

    @override
    async def get_metadata(self) -> ApifyRequestQueueMetadata:
        """Get metadata about the request queue.

        Returns:
            Metadata from the API, merged with local estimation, because in some cases, the data from the API can
            be delayed.
        """
        response = await self._api_client.get()
        if response is None:
            raise ValueError('Failed to fetch request queue metadata from the API.')
        # Enhance API response by local estimations (API can be delayed few seconds, while local estimation not.)
        return ApifyRequestQueueMetadata(
            id=response['id'],
            name=response['name'],
            total_request_count=max(response['totalRequestCount'], self._metadata.total_request_count),
            handled_request_count=max(response['handledRequestCount'], self._metadata.handled_request_count),
            pending_request_count=response['pendingRequestCount'],
            created_at=min(response['createdAt'], self._metadata.created_at),
            modified_at=max(response['modifiedAt'], self._metadata.modified_at),
            accessed_at=max(response['accessedAt'], self._metadata.accessed_at),
            had_multiple_clients=response['hadMultipleClients'] or self._metadata.had_multiple_clients,
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

        This method creates and initializes a new instance of the Apify request queue client. It handles
        authentication, storage lookup/creation, and metadata retrieval, and sets up internal caching and queue
        management structures.

        Args:
            id: The ID of the RQ to open. If provided, searches for existing RQ by ID.
                Mutually exclusive with name and alias.
            name: The name of the RQ to open (global scope, persists across runs).
                Mutually exclusive with id and alias.
            alias: The alias of the RQ to open (run scope, creates unnamed storage).
                Mutually exclusive with id and name.
            configuration: The configuration object containing API credentials and settings. Must include a valid
                `token` and `api_base_url`. May also contain a `default_request_queue_id` for fallback when neither
                `id`, `name`, nor `alias` is provided.
            access: Controls the implementation of the request queue client based on expected scenario:
                - 'single' is suitable for single consumer scenarios. It makes less API calls, is cheaper and faster.
                - 'shared' is suitable for multiple consumers scenarios at the cost of higher API usage.
                Detailed constraints for the 'single' access type:
                - Only one client is consuming the request queue at the time.
                - Multiple producers can put requests to the queue, but their forefront requests are not guaranteed to
                  be handled so quickly as this client does not aggressively fetch the forefront and relies on local
                  head estimation.
                - Requests are only added to the queue, never deleted by other clients. (Marking as handled is ok.)
                - Other producers can add new requests, but not modify existing ones.
                  (Modifications would not be included in local cache)

        Returns:
            An instance for the opened or created storage client.

        Raises:
            ValueError: If the configuration is missing required fields (token, api_base_url), if more than one of
                `id`, `name`, or `alias` is provided, or if none are provided and no default storage ID is available
                in the configuration.
        """
        if sum(1 for param in [id, name, alias] if param is not None) > 1:
            raise ValueError('Only one of "id", "name", or "alias" can be specified, not multiple.')

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

        # Normalize unnamed default storage in cases where not defined in `configuration.default_request_queue_id` to
        # unnamed storage aliased as `__default__`
        if not any([alias, name, id, configuration.default_request_queue_id]):
            alias = '__default__'

        if alias:
            # Check if there is pre-existing alias mapping in the default KVS.
            async with AliasResolver(storage_type=RequestQueue, alias=alias, configuration=configuration) as _alias:
                id = await _alias.resolve_id()

                # There was no pre-existing alias in the mapping.
                # Create a new unnamed storage and store the mapping.
                if id is None:
                    new_storage_metadata = RequestQueueMetadata.model_validate(
                        await apify_rqs_client.get_or_create(),
                    )
                    id = new_storage_metadata.id
                    await _alias.store_mapping(storage_id=id)

        # If name is provided, get or create the storage by name.
        elif name:
            id = RequestQueueMetadata.model_validate(
                await apify_rqs_client.get_or_create(name=name),
            ).id

        # If none are provided, try to get the default storage ID from environment variables.
        elif id is None:
            id = configuration.default_request_queue_id
            if not id:
                raise ValueError(
                    'RequestQueue "id", "name", or "alias" must be specified, '
                    'or a default default_request_queue_id ID must be set in the configuration.'
                )

        # Use suitable client_key to make `hadMultipleClients` response of Apify API useful.
        # It should persist across migrated or resurrected Actor runs on the Apify platform.
        _api_max_client_key_length = 32
        client_key = (configuration.actor_run_id or crypto_random_object_id(length=_api_max_client_key_length))[
            :_api_max_client_key_length
        ]

        apify_rq_client = apify_client_async.request_queue(request_queue_id=id, client_key=client_key)

        # Fetch its metadata.
        metadata = await apify_rq_client.get()

        # If metadata is None, it means the storage does not exist, so we create it.
        if metadata is None:
            id = RequestQueueMetadata.model_validate(
                await apify_rqs_client.get_or_create(),
            ).id
            apify_rq_client = apify_client_async.request_queue(request_queue_id=id, client_key=client_key)

        # Verify that the storage exists by fetching its metadata again.
        metadata = await apify_rq_client.get()
        if metadata is None:
            raise ValueError(f'Opening request queue with id={id}, name={name}, and alias={alias} failed.')

        metadata_model = RequestQueueMetadata.model_validate(metadata)

        return cls(api_client=apify_rq_client, metadata=metadata_model, access=access)

    @override
    async def purge(self) -> None:
        raise NotImplementedError(
            'Purging the request queue is not supported in the Apify platform. '
            'Use the `drop` method to delete the request queue instead.'
        )

    @override
    async def drop(self) -> None:
        await self._api_client.delete()
