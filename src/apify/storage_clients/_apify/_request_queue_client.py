from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
from logging import getLogger
from typing import TYPE_CHECKING, Final, Literal

from cachetools import LRUCache
from typing_extensions import override

from crawlee.storage_clients._base import RequestQueueClient
from crawlee.storage_clients.models import AddRequestsResponse, ProcessedRequest

from ._api_client_creation import create_storage_api_client
from ._models import ApifyRequestQueueMetadata, CachedRequest, RequestQueueHead, RequestQueueStats
from ._utils import unique_key_to_request_id
from apify import Request

if TYPE_CHECKING:
    from collections.abc import Sequence

    from apify_client.clients import RequestQueueClientAsync
    from crawlee.storage_clients.models import RequestQueueMetadata

    from apify import Configuration

logger = getLogger(__name__)


class ApifyRequestQueueClient(RequestQueueClient):
    """Base class for Apify platform implementations of the request queue client."""

    _MAX_CACHED_REQUESTS: Final[int] = 1_000_000
    """Maximum number of requests that can be cached."""

    _DEFAULT_LOCK_TIME: Final[timedelta] = timedelta(minutes=3)
    """The default lock time for requests in the queue."""

    _MAX_HEAD_ITEMS: Final[int] = 1000
    """The maximum head items read count limited by API."""

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

        self._access = access
        """The access mode for the request queue client."""

        self._metadata = metadata
        """Additional data related to the RequestQueue."""

        # Common attributes
        self._requests_cache: LRUCache[str, Request | CachedRequest] = LRUCache(maxsize=self._MAX_CACHED_REQUESTS)
        """A cache to store request objects. Request id is used as the cache key."""

        # Single client specific attributes
        self._head_requests: deque[str] = deque()
        """Ordered ids of requests that represent queue head (single mode)."""

        self._requests_already_handled: set[str] = set()
        """Local estimation of requests unique keys that are already present and handled on the platform."""

        self._requests_in_progress: set[str] = set()
        """Set of requests ids that are being processed locally (single mode)."""

        self._initialized_caches = False
        """This flag indicates whether the local caches were already initialized (single mode)."""

        # Shared client specific attributes
        self._queue_head: deque[str] = deque()
        """A deque to store request ids in the queue head (shared mode)."""

        self._queue_has_locked_requests: bool | None = None
        """Whether the queue has requests locked by another client (shared mode)."""

        self._should_check_for_forefront_requests = False
        """Whether to check for forefront requests in the next list_head call (shared mode)."""

        self._fetch_lock = asyncio.Lock()
        """Fetch lock to minimize race conditions when communicating with API (shared mode)."""

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
        api_client = await create_storage_api_client(
            storage_type='RequestQueue',
            configuration=configuration,
            alias=alias,
            name=name,
            id=id,
        )

        # Fetch metadata separately
        raw_metadata = await api_client.get()
        if raw_metadata is None:
            raise ValueError('Failed to retrieve request queue metadata')
        metadata = ApifyRequestQueueMetadata.model_validate(raw_metadata)

        return cls(
            api_client=api_client,
            metadata=metadata,
            access=access,
        )

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

        # Enhance API response by local estimations (API can be delayed few seconds, while local estimation not).
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

    @override
    async def drop(self) -> None:
        await self._api_client.delete()

    @override
    async def purge(self) -> None:
        raise NotImplementedError(
            'Purging the request queue is not supported in the Apify platform. '
            'Use the `drop` method to delete the request queue instead.'
        )

    @override
    async def add_batch_of_requests(
        self,
        requests: Sequence[Request],
        *,
        forefront: bool = False,
    ) -> AddRequestsResponse:
        if self._access == 'single':
            return await self._add_batch_of_requests_single(requests, forefront=forefront)

        if self._access == 'shared':
            return await self._add_batch_of_requests_shared(requests, forefront=forefront)

        raise ValueError(f'Unknown access type: {self._access}')

    @override
    async def get_request(self, unique_key: str) -> Request | None:
        if self._access == 'single':
            return await self._get_request_single(unique_key)

        if self._access == 'shared':
            return await self._get_request_shared(unique_key)

        raise ValueError(f'Unknown access type: {self._access}')

    @override
    async def fetch_next_request(self) -> Request | None:
        if self._access == 'single':
            return await self._fetch_next_request_single()

        if self._access == 'shared':
            return await self._fetch_next_request_shared()

        raise ValueError(f'Unknown access type: {self._access}')

    @override
    async def mark_request_as_handled(self, request: Request) -> ProcessedRequest | None:
        if self._access == 'single':
            return await self._mark_request_as_handled_single(request)

        if self._access == 'shared':
            return await self._mark_request_as_handled_shared(request)

        raise ValueError(f'Unknown access type: {self._access}')

    @override
    async def reclaim_request(
        self,
        request: Request,
        *,
        forefront: bool = False,
    ) -> ProcessedRequest | None:
        if self._access == 'single':
            return await self._reclaim_request_single(request, forefront=forefront)

        if self._access == 'shared':
            return await self._reclaim_request_shared(request, forefront=forefront)

        raise ValueError(f'Unknown access type: {self._access}')

    @override
    async def is_empty(self) -> bool:
        if self._access == 'single':
            return await self._is_empty_single()

        if self._access == 'shared':
            return await self._is_empty_shared()

        raise ValueError(f'Unknown access type: {self._access}')

    async def _init_caches_single(self) -> None:
        """Initialize the local caches by getting requests from the existing queue."""
        response = await self._api_client.list_requests(limit=10_000)
        for request_data in response.get('items', []):
            request = Request.model_validate(request_data)
            request_id = request_data['id']

            if request.was_already_handled:
                # Cache just id for deduplication
                self._requests_already_handled.add(request_id)
            else:
                # Cache full request
                self._requests_cache[request_id] = request

    async def _add_batch_of_requests_single(
        self,
        requests: Sequence[Request],
        *,
        forefront: bool = False,
    ) -> AddRequestsResponse:
        """Add a batch of requests to the queue (single client mode)."""
        if not self._initialized_caches:
            # One time process to initialize local caches for existing request queues.
            await self._init_caches_single()
            self._initialized_caches = True

        new_requests: list[Request] = []
        already_present_requests: list[ProcessedRequest] = []

        for request in requests:
            # Calculate id for request
            request_id = unique_key_to_request_id(request.unique_key)

            # Check if request is known to be already handled (it has to be present as well.)
            if request_id in self._requests_already_handled:
                already_present_requests.append(
                    ProcessedRequest(
                        id=request_id,
                        unique_key=request.unique_key,
                        was_already_present=True,
                        was_already_handled=True,
                    )
                )
            # Check if request is known to be already present, but unhandled
            elif self._requests_cache.get(request_id):
                already_present_requests.append(
                    ProcessedRequest(
                        id=request_id,
                        unique_key=request.unique_key,
                        was_already_present=True,
                        was_already_handled=request.was_already_handled,
                    )
                )
            else:
                # Push the request to the platform. Probably not there, or we are not aware of it
                new_requests.append(request)

                # Update local caches
                self._requests_cache[request_id] = request
                if forefront:
                    self._head_requests.append(request_id)
                else:
                    self._head_requests.appendleft(request_id)

        if new_requests:
            # Prepare requests for API by converting to dictionaries.
            requests_dict = [
                request.model_dump(
                    by_alias=True,
                )
                for request in new_requests
            ]

            # Send requests to API.
            api_response = AddRequestsResponse.model_validate(
                await self._api_client.batch_add_requests(requests=requests_dict, forefront=forefront)
            )
            # Add the locally known already present processed requests based on the local cache.
            api_response.processed_requests.extend(already_present_requests)
            # Remove unprocessed requests from the cache
            for unprocessed_request in api_response.unprocessed_requests:
                self._requests_cache.pop(unique_key_to_request_id(unprocessed_request.unique_key), None)

        else:
            api_response = AddRequestsResponse(
                unprocessed_requests=[],
                processed_requests=already_present_requests,
            )

        # Update assumed total count for newly added requests.
        new_request_count = 0
        for processed_request in api_response.processed_requests:
            if not processed_request.was_already_present and not processed_request.was_already_handled:
                new_request_count += 1
        self._metadata.total_request_count += new_request_count
        self._metadata.pending_request_count += new_request_count

        return api_response

    async def _get_request_single(self, unique_key: str) -> Request | None:
        """Get a request by unique key (single client mode)."""
        return await self._get_request_by_id_single(id=unique_key_to_request_id(unique_key))

    async def _fetch_next_request_single(self) -> Request | None:
        """Return the next request in the queue to be processed (single client mode)."""
        await self._ensure_head_is_non_empty_single()

        while self._head_requests:
            request_id = self._head_requests.pop()
            if request_id not in self._requests_in_progress and request_id not in self._requests_already_handled:
                self._requests_in_progress.add(request_id)
                return await self._get_request_by_id_single(request_id)
        # No request locally and the ones returned from the platform are already in progress.
        return None

    async def _mark_request_as_handled_single(self, request: Request) -> ProcessedRequest | None:
        """Mark a request as handled after successful processing (single client mode)."""
        request_id = unique_key_to_request_id(request.unique_key)

        if request.handled_at is None:
            request.handled_at = datetime.now(tz=timezone.utc)
            self._metadata.handled_request_count += 1
            self._metadata.pending_request_count -= 1

        cached_request = self._requests_cache.get(request_id)
        if cached_request and isinstance(cached_request, Request):
            cached_request.handled_at = request.handled_at

        try:
            # Update the request in the API
            processed_request = await self._update_request(request)
            # Remember that we handled this request, to optimize local deduplication.
            self._requests_already_handled.add(request_id)
            # Remove request from cache. It will most likely not be needed.
            self._requests_cache.pop(request_id, None)
            self._requests_in_progress.discard(request_id)

        except Exception as exc:
            logger.debug(f'Error marking request {request.unique_key} as handled: {exc!s}')
            return None
        else:
            return processed_request

    async def _reclaim_request_single(
        self,
        request: Request,
        *,
        forefront: bool = False,
    ) -> ProcessedRequest | None:
        """Reclaim a failed request back to the queue (single client mode)."""
        request_id = unique_key_to_request_id(request.unique_key)

        if request.was_already_handled:
            request.handled_at = None

        try:
            # Make sure request is in the local cache. We might need it.
            self._requests_cache[request_id] = request

            # No longer in progress
            self._requests_in_progress.discard(request_id)
            # No longer handled
            self._requests_already_handled.discard(request_id)

            if forefront:
                # Append to top of the local head estimation
                self._head_requests.append(request_id)

            processed_request = await self._update_request(request, forefront=forefront)
            processed_request.id = request_id
            processed_request.unique_key = request.unique_key
            # If the request was previously handled, decrement our handled count since
            # we're putting it back for processing.
            if request.was_already_handled and not processed_request.was_already_handled:
                self._metadata.handled_request_count -= 1
                self._metadata.pending_request_count += 1

        except Exception as exc:
            logger.debug(f'Error reclaiming request {request.unique_key}: {exc!s}')
            return None
        else:
            return processed_request

    async def _is_empty_single(self) -> bool:
        """Check if the queue is empty (single client mode)."""
        await self._ensure_head_is_non_empty_single()
        return not self._head_requests and not self._requests_in_progress

    async def _ensure_head_is_non_empty_single(self) -> None:
        """Ensure that the queue head has requests if they are available in the queue."""
        if len(self._head_requests) <= 1:
            await self._list_head_single()

    async def _list_head_single(self) -> None:
        """List the head of the queue for single client mode."""
        desired_new_head_items = 200
        # The head will contain in progress requests as well, so we need to fetch more, to get some new ones.
        requested_head_items = max(self._MAX_HEAD_ITEMS, desired_new_head_items + len(self._requests_in_progress))
        response = await self._api_client.list_head(limit=requested_head_items)

        # Update metadata
        # Check if there is another client working with the RequestQueue
        self._metadata.had_multiple_clients = response.get('hadMultipleClients', False)

        if modified_at := response.get('queueModifiedAt'):
            self._metadata.modified_at = max(self._metadata.modified_at, modified_at)

        # Update the cached data
        for request_data in response.get('items', []):
            request = Request.model_validate(request_data)
            request_id = request_data['id']

            if request_id in self._requests_in_progress:
                # Ignore requests that are already in progress, we will not process them again.
                continue

            if request.was_already_handled:
                # Do not cache fully handled requests, we do not need them. Just cache their id.
                self._requests_already_handled.add(request_id)
            # Add new requests to the end of the head, unless already present in head
            elif request_id not in self._head_requests:
                self._head_requests.appendleft(request_id)

    async def _get_request_by_id_single(self, id: str) -> Request | None:
        """Get a request by id (single client mode)."""
        if id in self._requests_cache:
            cached = self._requests_cache[id]
            if isinstance(cached, Request):
                return cached

        # Requests that were not added by this client are not in local cache. Fetch them from platform.
        response = await self._api_client.get_request(id)

        if response is None:
            return None

        request = Request.model_validate(response)

        # Updated local caches
        if id in self._requests_in_progress:
            # No caching of requests that are already in progress, client is already aware of them.
            pass
        elif request.was_already_handled:
            # Cache only id for already handled requests
            self._requests_already_handled.add(id)
        else:
            # Cache full request for unhandled requests that are not yet in progress and are not yet handled.
            self._requests_cache[id] = request
        return request

    # Shared client implementation methods
    async def _add_batch_of_requests_shared(
        self,
        requests: Sequence[Request],
        *,
        forefront: bool = False,
    ) -> AddRequestsResponse:
        """Add a batch of requests to the queue (shared client mode)."""
        # Do not try to add previously added requests to avoid pointless expensive calls to API
        new_requests: list[Request] = []
        already_present_requests: list[ProcessedRequest] = []

        for request in requests:
            request_id = unique_key_to_request_id(request.unique_key)
            if self._requests_cache.get(request_id):
                # We are not sure if it was already handled at this point, and it is not worth calling API for it.
                # It could have been handled by another client in the meantime, so cached information about
                # `request.was_already_handled` is not reliable.
                already_present_requests.append(
                    ProcessedRequest(
                        id=request_id,
                        unique_key=request.unique_key,
                        was_already_present=True,
                        was_already_handled=request.was_already_handled,
                    )
                )

            else:
                # Add new request to the cache.
                processed_request = ProcessedRequest(
                    id=request_id,
                    unique_key=request.unique_key,
                    was_already_present=True,
                    was_already_handled=request.was_already_handled,
                )
                self._cache_request(
                    request_id,
                    processed_request,
                )
                new_requests.append(request)

        if new_requests:
            # Prepare requests for API by converting to dictionaries.
            requests_dict = [
                request.model_dump(
                    by_alias=True,
                )
                for request in new_requests
            ]

            # Send requests to API.
            api_response = AddRequestsResponse.model_validate(
                await self._api_client.batch_add_requests(requests=requests_dict, forefront=forefront)
            )

            # Add the locally known already present processed requests based on the local cache.
            api_response.processed_requests.extend(already_present_requests)

            # Remove unprocessed requests from the cache
            for unprocessed_request in api_response.unprocessed_requests:
                unprocessed_request_id = unique_key_to_request_id(unprocessed_request.unique_key)
                self._requests_cache.pop(unprocessed_request_id, None)

        else:
            api_response = AddRequestsResponse.model_validate(
                {'unprocessedRequests': [], 'processedRequests': already_present_requests}
            )

        logger.debug(
            f'Tried to add new requests: {len(new_requests)}, '
            f'succeeded to add new requests: {len(api_response.processed_requests) - len(already_present_requests)}, '
            f'skipped already present requests: {len(already_present_requests)}'
        )

        # Update assumed total count for newly added requests.
        new_request_count = 0
        for processed_request in api_response.processed_requests:
            if not processed_request.was_already_present and not processed_request.was_already_handled:
                new_request_count += 1

        self._metadata.total_request_count += new_request_count
        self._metadata.pending_request_count += new_request_count

        return api_response

    async def _get_request_shared(self, unique_key: str) -> Request | None:
        """Get a request by unique key (shared client mode)."""
        return await self._get_request_by_id_shared(unique_key_to_request_id(unique_key))

    async def _fetch_next_request_shared(self) -> Request | None:
        """Return the next request in the queue to be processed (shared client mode)."""
        # Ensure the queue head has requests if available. Fetching the head with lock to prevent race conditions.
        async with self._fetch_lock:
            await self._ensure_head_is_non_empty_shared()

            # If queue head is empty after ensuring, there are no requests
            if not self._queue_head:
                return None

            # Get the next request ID from the queue head
            next_request_id = self._queue_head.popleft()

        request = await self._get_or_hydrate_request(next_request_id)

        # Handle potential inconsistency where request might not be in the main table yet
        if request is None:
            logger.debug(
                'Cannot find a request from the beginning of queue, will be retried later',
                extra={'next_request_id': next_request_id},
            )
            return None

        # If the request was already handled, skip it
        if request.handled_at is not None:
            logger.debug(
                'Request fetched from the beginning of queue was already handled',
                extra={'next_request_id': next_request_id},
            )
            return None

        # Use get request to ensure we have the full request object.
        request = await self._get_request_by_id_shared(next_request_id)
        if request is None:
            logger.debug(
                'Request fetched from the beginning of queue was not found in the RQ',
                extra={'next_request_id': next_request_id},
            )
            return None

        return request

    async def _mark_request_as_handled_shared(self, request: Request) -> ProcessedRequest | None:
        """Mark a request as handled after successful processing (shared client mode)."""
        request_id = unique_key_to_request_id(request.unique_key)
        # Set the handled_at timestamp if not already set
        if request.handled_at is None:
            request.handled_at = datetime.now(tz=timezone.utc)

        cached_request = self._requests_cache.get(request_id)
        if cached_request and isinstance(cached_request, CachedRequest):
            cached_request.was_already_handled = request.was_already_handled
        try:
            # Update the request in the API
            processed_request = await self._update_request(request)
            processed_request.id = request_id
            processed_request.unique_key = request.unique_key

            # Update assumed handled count if this wasn't already handled
            if not processed_request.was_already_handled:
                self._metadata.handled_request_count += 1
                self._metadata.pending_request_count -= 1

            # Update the cache with the handled request
            self._cache_request(
                cache_key=request_id,
                processed_request=processed_request,
                hydrated_request=request,
            )
        except Exception as exc:
            logger.debug(f'Error marking request {request.unique_key} as handled: {exc!s}')
            return None
        else:
            return processed_request

    async def _reclaim_request_shared(
        self,
        request: Request,
        *,
        forefront: bool = False,
    ) -> ProcessedRequest | None:
        """Reclaim a failed request back to the queue (shared client mode)."""
        # Check if the request was marked as handled and clear it. When reclaiming,
        # we want to put the request back for processing.
        if request.was_already_handled:
            request.handled_at = None

        # Reclaim with lock to prevent race conditions that could lead to double processing of the same request.
        async with self._fetch_lock:
            try:
                # Update the request in the API.
                processed_request = await self._update_request(request, forefront=forefront)
                processed_request.unique_key = request.unique_key

                # If the request was previously handled, decrement our handled count since
                # we're putting it back for processing.
                if request.was_already_handled and not processed_request.was_already_handled:
                    self._metadata.handled_request_count -= 1
                    self._metadata.pending_request_count += 1

                # Update the cache
                cache_key = request.unique_key
                self._cache_request(
                    cache_key,
                    processed_request,
                    hydrated_request=request,
                )

                # If we're adding to the forefront, we need to check for forefront requests
                # in the next list_head call
                if forefront:
                    self._should_check_for_forefront_requests = True

            except Exception as exc:
                logger.debug(f'Error reclaiming request {request.unique_key}: {exc!s}')
                return None
            else:
                return processed_request

    async def _is_empty_shared(self) -> bool:
        """Check if the queue is empty (shared client mode)."""
        # Check _list_head.
        # Without the lock the `is_empty` is prone to falsely report True with some low probability race condition.
        async with self._fetch_lock:
            head = await self._list_head_shared(limit=1)
            return len(head.items) == 0 and not self._queue_has_locked_requests

    async def _get_metadata_estimate(self) -> RequestQueueMetadata:
        """Try to get cached metadata first. If multiple clients, fuse with global metadata."""
        if self._metadata.had_multiple_clients:
            return await self.get_metadata()
        # Get local estimation (will not include changes done by another client)
        return self._metadata

    async def _ensure_head_is_non_empty_shared(self) -> None:
        """Ensure that the queue head has requests if they are available in the queue."""
        # If queue head has adequate requests, skip fetching more
        if len(self._queue_head) > 1 and not self._should_check_for_forefront_requests:
            return

        # Fetch requests from the API and populate the queue head
        await self._list_head_shared()

    async def _get_or_hydrate_request(self, request_id: str) -> Request | None:
        """Get a request by id, either from cache or by fetching from API."""
        # First check if the request is in our cache
        cached_entry = self._requests_cache.get(request_id)

        if cached_entry and isinstance(cached_entry, CachedRequest) and cached_entry.hydrated:
            # If we have the request hydrated in cache, return it
            return cached_entry.hydrated

        # If not in cache or not hydrated, fetch the request
        try:
            # Fetch the request data
            request = await self._get_request_by_id_shared(request_id)

            # If request is not found and return None
            if not request:
                return None

            # Update cache with hydrated request
            self._cache_request(
                cache_key=request_id,
                processed_request=ProcessedRequest(
                    id=request_id,
                    unique_key=request.unique_key,
                    was_already_present=True,
                    was_already_handled=request.handled_at is not None,
                ),
                hydrated_request=request,
            )
        except Exception as exc:
            logger.debug(f'Error fetching request {request_id}: {exc!s}')
            return None
        else:
            return request

    async def _list_head_shared(
        self,
        *,
        limit: int = 25,
    ) -> RequestQueueHead:
        """Retrieve requests from the beginning of the queue (shared client mode)."""
        # Return from cache if available and we're not checking for new forefront requests
        if self._queue_head and not self._should_check_for_forefront_requests:
            logger.debug(f'Using cached queue head with {len(self._queue_head)} requests')
            # Create a list of requests from the cached queue head
            items = []
            for request_id in list(self._queue_head)[:limit]:
                cached_request = self._requests_cache.get(request_id)
                if cached_request and isinstance(cached_request, CachedRequest) and cached_request.hydrated:
                    items.append(cached_request.hydrated)

            metadata = await self._get_metadata_estimate()

            return RequestQueueHead(
                limit=limit,
                had_multiple_clients=metadata.had_multiple_clients,
                queue_modified_at=metadata.modified_at,
                items=items,
                lock_time=None,
                queue_has_locked_requests=self._queue_has_locked_requests,
            )
        leftover_buffer = list[str]()
        if self._should_check_for_forefront_requests:
            leftover_buffer = list(self._queue_head)
            self._queue_head.clear()
            self._should_check_for_forefront_requests = False

        # Otherwise fetch from API
        response = await self._api_client.list_and_lock_head(
            lock_secs=int(self._DEFAULT_LOCK_TIME.total_seconds()),
            limit=limit,
        )

        # Update the queue head cache
        self._queue_has_locked_requests = response.get('queueHasLockedRequests', False)
        # Check if there is another client working with the RequestQueue
        self._metadata.had_multiple_clients = response.get('hadMultipleClients', False)

        for request_data in response.get('items', []):
            request = Request.model_validate(request_data)
            request_id = request_data.get('id')

            # Skip requests without ID or unique key
            if not request.unique_key or not request_id:
                logger.debug(
                    'Skipping request from queue head, missing unique key or id',
                    extra={
                        'unique_key': request.unique_key,
                        'id': request_id,
                    },
                )
                continue

            # Cache the request
            self._cache_request(
                request_id,
                ProcessedRequest(
                    id=request_id,
                    unique_key=request.unique_key,
                    was_already_present=True,
                    was_already_handled=False,
                ),
                hydrated_request=request,
            )
            self._queue_head.append(request_id)

        for leftover_id in leftover_buffer:
            # After adding new requests to the forefront, any existing leftover locked request is kept in the end.
            self._queue_head.append(leftover_id)
        return RequestQueueHead.model_validate(response)

    def _cache_request(
        self,
        cache_key: str,
        processed_request: ProcessedRequest,
        *,
        hydrated_request: Request | None = None,
    ) -> None:
        """Cache a request for future use."""
        self._requests_cache[cache_key] = CachedRequest(
            id=processed_request.id or cache_key,
            was_already_handled=processed_request.was_already_handled,
            hydrated=hydrated_request,
            lock_expires_at=None,
        )

    async def _get_request_by_id_shared(self, request_id: str) -> Request | None:
        """Get a request by id (shared client mode)."""
        response = await self._api_client.get_request(request_id)

        if response is None:
            return None

        return Request.model_validate(response)

    async def _update_request(
        self,
        request: Request,
        *,
        forefront: bool = False,
    ) -> ProcessedRequest:
        """Update a request in the queue."""
        request_dict = request.model_dump(by_alias=True)
        request_dict['id'] = unique_key_to_request_id(request.unique_key)
        response = await self._api_client.update_request(request=request_dict, forefront=forefront)
        return ProcessedRequest.model_validate({'uniqueKey': request.unique_key} | response)
