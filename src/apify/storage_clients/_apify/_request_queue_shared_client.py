from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
from logging import getLogger
from typing import TYPE_CHECKING, Any, Final

from cachetools import LRUCache

from crawlee.storage_clients.models import AddRequestsResponse, ProcessedRequest, RequestQueueMetadata

from ._models import ApifyRequestQueueMetadata, CachedRequest, RequestQueueHead
from ._utils import unique_key_to_request_id
from apify import Request

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Sequence

    from apify_client.clients import RequestQueueClientAsync


logger = getLogger(__name__)


class ApifyRequestQueueSharedClient:
    """An Apify platform implementation of the request queue client.

    This implementation supports multiple producers and multiple consumers scenario.
    """

    _DEFAULT_LOCK_TIME: Final[timedelta] = timedelta(minutes=3)
    """The default lock time for requests in the queue."""

    def __init__(
        self,
        *,
        api_client: RequestQueueClientAsync,
        metadata: RequestQueueMetadata,
        cache_size: int,
        metadata_getter: Callable[[], Coroutine[Any, Any, ApifyRequestQueueMetadata]],
    ) -> None:
        """Initialize a new instance.

        Preferably use the `ApifyRequestQueueClient.open` class method to create a new instance.
        """
        self.metadata = metadata
        """Additional data related to the RequestQueue."""

        self._metadata_getter = metadata_getter
        """Async function to get metadata from API."""

        self._api_client = api_client
        """The Apify request queue client for API operations."""

        self._queue_head = deque[str]()
        """A deque to store request ids in the queue head."""

        self._requests_cache: LRUCache[str, CachedRequest] = LRUCache(maxsize=cache_size)
        """A cache to store request objects. Request id is used as the cache key."""

        self._queue_has_locked_requests: bool | None = None
        """Whether the queue has requests locked by another client."""

        self._should_check_for_forefront_requests = False
        """Whether to check for forefront requests in the next list_head call."""

        self._fetch_lock = asyncio.Lock()
        """Fetch lock to minimize race conditions when communicating with API."""

    async def _get_metadata_estimate(self) -> RequestQueueMetadata:
        """Try to get cached metadata first. If multiple clients, fuse with global metadata.

        This method is used internally to avoid unnecessary API call unless needed (multiple clients).
        Local estimation of metadata is without delay, unlike metadata from API. In situation where there is only one
        client, it is the better choice.
        """
        if self.metadata.had_multiple_clients:
            return await self._metadata_getter()
        # Get local estimation (will not include changes done bo another client)
        return self.metadata

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

        self.metadata.total_request_count += new_request_count
        self.metadata.pending_request_count += new_request_count

        return api_response

    async def get_request(self, unique_key: str) -> Request | None:
        """Get a request by unique key.

        Args:
            unique_key: Unique key of the request to get.

        Returns:
            The request or None if not found.
        """
        return await self._get_request_by_id(unique_key_to_request_id(unique_key))

    async def _get_request_by_id(self, request_id: str) -> Request | None:
        response = await self._api_client.get_request(request_id)

        if response is None:
            return None

        return Request.model_validate(response)

    async def fetch_next_request(self) -> Request | None:
        """Return the next request in the queue to be processed.

        Once you successfully finish processing of the request, you need to call `mark_request_as_handled`
        to mark the request as handled in the queue. If there was some error in processing the request, call
        `reclaim_request` instead, so that the queue will give the request to some other consumer
        in another call to the `fetch_next_request` method.

        Returns:
            The request or `None` if there are no more pending requests.
        """
        # Ensure the queue head has requests if available. Fetching the head with lock to prevent race conditions.
        async with self._fetch_lock:
            await self._ensure_head_is_non_empty()

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
        request = await self._get_request_by_id(next_request_id)
        if request is None:
            logger.debug(
                'Request fetched from the beginning of queue was not found in the RQ',
                extra={'next_request_id': next_request_id},
            )
            return None

        return request

    async def mark_request_as_handled(self, request: Request) -> ProcessedRequest | None:
        """Mark a request as handled after successful processing.

        Handled requests will never again be returned by the `fetch_next_request` method.

        Args:
            request: The request to mark as handled.

        Returns:
            Information about the queue operation. `None` if the given request was not in progress.
        """
        request_id = unique_key_to_request_id(request.unique_key)
        # Set the handled_at timestamp if not already set
        if request.handled_at is None:
            request.handled_at = datetime.now(tz=timezone.utc)

        if cached_request := self._requests_cache[request_id]:
            cached_request.was_already_handled = request.was_already_handled
        try:
            # Update the request in the API
            processed_request = await self._update_request(request)
            processed_request.id = request_id
            processed_request.unique_key = request.unique_key

            # Update assumed handled count if this wasn't already handled
            if not processed_request.was_already_handled:
                self.metadata.handled_request_count += 1
                self.metadata.pending_request_count -= 1

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
                    self.metadata.handled_request_count -= 1
                    self.metadata.pending_request_count += 1

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

    async def is_empty(self) -> bool:
        """Check if the queue is empty.

        Returns:
            True if the queue is empty, False otherwise.
        """
        # Check _list_head.
        # Without the lock the `is_empty` is prone to falsely report True with some low probability race condition.
        async with self._fetch_lock:
            head = await self._list_head(limit=1)
            return len(head.items) == 0 and not self._queue_has_locked_requests

    async def _ensure_head_is_non_empty(self) -> None:
        """Ensure that the queue head has requests if they are available in the queue."""
        # If queue head has adequate requests, skip fetching more
        if len(self._queue_head) > 1 and not self._should_check_for_forefront_requests:
            return

        # Fetch requests from the API and populate the queue head
        await self._list_head()

    async def _get_or_hydrate_request(self, request_id: str) -> Request | None:
        """Get a request by id, either from cache or by fetching from API.

        Args:
            request_id: Id of the request to get.

        Returns:
            The request if found and valid, otherwise None.
        """
        # First check if the request is in our cache
        cached_entry = self._requests_cache.get(request_id)

        if cached_entry and cached_entry.hydrated:
            # If we have the request hydrated in cache, return it
            return cached_entry.hydrated

        # If not in cache or not hydrated, fetch the request
        try:
            # Fetch the request data
            request = await self._get_request_by_id(request_id)

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

    async def _update_request(
        self,
        request: Request,
        *,
        forefront: bool = False,
    ) -> ProcessedRequest:
        """Update a request in the queue.

        Args:
            request: The updated request.
            forefront: Whether to put the updated request in the beginning or the end of the queue.

        Returns:
            The updated request
        """
        request_dict = request.model_dump(by_alias=True)
        request_dict['id'] = unique_key_to_request_id(request.unique_key)
        response = await self._api_client.update_request(
            request=request_dict,
            forefront=forefront,
        )

        return ProcessedRequest.model_validate(
            {'uniqueKey': request.unique_key} | response,
        )

    async def _list_head(
        self,
        *,
        limit: int = 25,
    ) -> RequestQueueHead:
        """Retrieve requests from the beginning of the queue.

        Args:
            limit: Maximum number of requests to retrieve.

        Returns:
            A collection of requests from the beginning of the queue.
        """
        # Return from cache if available and we're not checking for new forefront requests
        if self._queue_head and not self._should_check_for_forefront_requests:
            logger.debug(f'Using cached queue head with {len(self._queue_head)} requests')
            # Create a list of requests from the cached queue head
            items = []
            for request_id in list(self._queue_head)[:limit]:
                cached_request = self._requests_cache.get(request_id)
                if cached_request and cached_request.hydrated:
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
        self.metadata.had_multiple_clients = response.get('hadMultipleClients', False)

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
        """Cache a request for future use.

        Args:
            cache_key: The key to use for caching the request. It should be request ID.
            processed_request: The processed request information.
            forefront: Whether the request was added to the forefront of the queue.
            hydrated_request: The hydrated request object, if available.
        """
        self._requests_cache[cache_key] = CachedRequest(
            id=processed_request.id,
            was_already_handled=processed_request.was_already_handled,
            hydrated=hydrated_request,
            lock_expires_at=None,
        )
