from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from logging import getLogger
from typing import TYPE_CHECKING, Final

from cachetools import LRUCache

from crawlee.storage_clients.models import AddRequestsResponse, ProcessedRequest, RequestQueueMetadata

from ._utils import unique_key_to_request_id
from apify import Request

if TYPE_CHECKING:
    from collections.abc import Sequence

    from apify_client.clients import RequestQueueClientAsync


logger = getLogger(__name__)


class ApifyRequestQueueSingleClient:
    """An Apify platform implementation of the request queue client with limited capability.

    This client is designed to use as little resources as possible, but has to be used in constrained context.
    Constraints:
    - Only one client is consuming the request queue at the time.
    - Multiple producers can put requests to the queue, but their forefront requests are not guaranteed to be handled
      so quickly as this client does not aggressively fetch the forefront and relies on local head estimation.
    - Requests are only added to the queue, never deleted. (Marking as handled is ok.)
    - Other producers can add new requests, but not modify existing ones (otherwise caching can miss the updates)

    If the constraints are not met, the client might work in an unpredictable way.
    """

    _MAX_HEAD_ITEMS: Final[int] = 1000
    """The maximum head items read count limited by API."""

    def __init__(
        self,
        *,
        api_client: RequestQueueClientAsync,
        metadata: RequestQueueMetadata,
        cache_size: int,
    ) -> None:
        """Initialize a new instance.

        Preferably use the `ApifyRequestQueueClient.open` class method to create a new instance.
        """
        self.metadata = metadata
        """Additional data related to the RequestQueue."""

        self._api_client = api_client
        """The Apify request queue client for API operations."""

        self._requests_cache: LRUCache[str, Request] = LRUCache(maxsize=cache_size)
        """A cache to store request objects. Request id is used as the cache key."""

        self._head_requests: deque[str] = deque()
        """Ordered ids of requests that represent queue head."""

        self._requests_already_handled: set[str] = set()
        """Local estimation of requests unique keys that are already present and handled on the platform.

        - To enhance local deduplication.
        - To reduce the _requests_cache size. Already handled requests are most likely not going to be needed again,
        so no need to cache more than their id.
        """

        self._requests_in_progress: set[str] = set()
        """Set of requests ids that are being processed locally.

        - To help decide if the RQ is finished or not. This is the only consumer, so it can be tracked locally.
        """

        self._initialized_caches = False
        """This flag indicates whether the local caches were already initialized.

        Initialization is done lazily only if deduplication is needed (When calling add_batch_of_requests).
        """

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
        if not self._initialized_caches:
            # One time process to initialize local caches for existing request queues.
            await self._init_caches()
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
        return await self._get_request(id=unique_key_to_request_id(unique_key))

    async def _get_request(self, id: str) -> Request | None:
        """Get a request by id.

        Args:
            id: Id of request to get.

        Returns:
            The request or None if not found.
        """
        if id in self._requests_cache:
            return self._requests_cache[id]

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

    async def fetch_next_request(self) -> Request | None:
        """Return the next request in the queue to be processed.

        Once you successfully finish processing of the request, you need to call `mark_request_as_handled`
        to mark the request as handled in the queue. If there was some error in processing the request, call
        `reclaim_request` instead, so that the queue will give the request to some other consumer
        in another call to the `fetch_next_request` method.

        Returns:
            The request or `None` if there are no more pending requests.
        """
        await self._ensure_head_is_non_empty()

        while self._head_requests:
            request_id = self._head_requests.pop()
            if request_id not in self._requests_in_progress and request_id not in self._requests_already_handled:
                self._requests_in_progress.add(request_id)
                return await self._get_request(request_id)
        # No request locally and the ones returned from the platform are already in progress.
        return None

    async def _ensure_head_is_non_empty(self) -> None:
        """Ensure that the queue head has requests if they are available in the queue."""
        if len(self._head_requests) <= 1:
            await self._list_head()

    async def _list_head(self) -> None:
        desired_new_head_items = 200
        # The head will contain in progress requests as well, so we need to fetch more, to get some new ones.
        requested_head_items = max(self._MAX_HEAD_ITEMS, desired_new_head_items + len(self._requests_in_progress))
        response = await self._api_client.list_head(limit=requested_head_items)

        # Update metadata
        # Check if there is another client working with the RequestQueue
        self.metadata.had_multiple_clients = response.get('hadMultipleClients', False)
        # Should warn once? This might be outside expected context if the other consumers consumes at the same time

        if modified_at := response.get('queueModifiedAt'):
            self.metadata.modified_at = max(self.metadata.modified_at, modified_at)

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

    async def mark_request_as_handled(self, request: Request) -> ProcessedRequest | None:
        """Mark a request as handled after successful processing.

        Handled requests will never again be returned by the `fetch_next_request` method.

        Args:
            request: The request to mark as handled.

        Returns:
            Information about the queue operation. `None` if the given request was not in progress.
        """
        # Set the handled_at timestamp if not already set

        request_id = unique_key_to_request_id(request.unique_key)

        if request.handled_at is None:
            request.handled_at = datetime.now(tz=timezone.utc)
            self.metadata.handled_request_count += 1
            self.metadata.pending_request_count -= 1

        if cached_request := self._requests_cache.get(request_id):
            cached_request.handled_at = request.handled_at

        try:
            # Update the request in the API
            # Works as upsert - adds the request if it does not exist yet. (Local request that was handled before
            # adding to the queue.)
            processed_request = await self._update_request(request)
            # Remember that we handled this request, to optimize local deduplication.
            self._requests_already_handled.add(request_id)
            # Remove request from cache. It will most likely not be needed.
            self._requests_cache.pop(request_id)
            self._requests_in_progress.discard(request_id)

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
                self.metadata.handled_request_count -= 1
                self.metadata.pending_request_count += 1

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
        # Without the lock the `is_empty` is prone to falsely report True with some low probability race condition.
        await self._ensure_head_is_non_empty()
        return not self._head_requests and not self._requests_in_progress

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

    async def _init_caches(self) -> None:
        """Initialize the local caches by getting requests from the existing queue.

        This is mainly done to improve local deduplication capability. List request can return up to 10k requests, but
        their order is implementation detail and does not respect head order or insertion order.

        Deduplication on platform is expensive, it takes 1 API call per request and 1 write operation per request.
        Local deduplication is cheaper, it takes 1 API call for whole cache and 1 read operation per request.
        """
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
