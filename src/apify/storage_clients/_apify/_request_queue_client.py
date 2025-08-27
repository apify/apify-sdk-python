from __future__ import annotations

import asyncio
import re
from base64 import b64encode
from collections import deque
from datetime import datetime, timezone
from hashlib import sha256
from logging import getLogger
from typing import TYPE_CHECKING, Final

from cachetools import LRUCache
from typing_extensions import override

from apify_client import ApifyClientAsync
from crawlee._utils.crypto import crypto_random_object_id
from crawlee.storage_clients._base import RequestQueueClient
from crawlee.storage_clients.models import AddRequestsResponse, ProcessedRequest, RequestQueueMetadata

from apify import Request

if TYPE_CHECKING:
    from collections.abc import Sequence

    from apify_client.clients import RequestQueueClientAsync

    from apify import Configuration

logger = getLogger(__name__)


def unique_key_to_request_id(unique_key: str, *, request_id_length: int = 15) -> str:
    """Generate a deterministic request ID based on a unique key.

    Args:
        unique_key: The unique key to convert into a request ID.
        request_id_length: The length of the request ID.

    Returns:
        A URL-safe, truncated request ID based on the unique key.
    """
    # Encode the unique key and compute its SHA-256 hash
    hashed_key = sha256(unique_key.encode('utf-8')).digest()

    # Encode the hash in base64 and decode it to get a string
    base64_encoded = b64encode(hashed_key).decode('utf-8')

    # Remove characters that are not URL-safe ('+', '/', or '=')
    url_safe_key = re.sub(r'(\+|\/|=)', '', base64_encoded)

    # Truncate the key to the desired length
    return url_safe_key[:request_id_length]


class ApifyRequestQueueClient(RequestQueueClient):
    """An Apify platform implementation of the request queue client with limited capability.

    This client is designed to use as little resources as possible, but has to be used in constrained context.
    Constraints:
    - Only one client is consuming the request queue at the time.
    - Multiple producers can put requests to the queue, but their forefront requests are not guaranteed to be handled
      sooner. (Explanation below)
    - This client always consumes first own requests and only if no local requests exists it tries to get requests from
      the global queue. ???
    - Requests are only added to the queue, never deleted. (Marking as handled is ok.)

    If the constraints are not met, the client might work in an unpredictable way.

    Optimization notes:
    - The client aggressively caches requests to avoid unnecessary API calls.
    - The client adds requests to the global queue if they are handled. (Potential optimization, but problematic,
     probably not worth it)
    - The client adds unhandled requests to the global queue only if local cache size reaches some threshold or based on
      external callback. (To prevent double API call per request - adding request to the global queue and marking it as
      handled. The client tries to do that in one step if possible.) (Potential optimization, but problematic,
       probably not worth it)
    - The client tracks own forefront (priority requests), that does not have to be in sync with the global forefront.
    """

    _MAX_HEAD_ITEMS: Final[int] = 200
    """The maximum head items read count limited by API."""

    _MAX_CACHED_REQUESTS: Final[int] = 1_000_000
    """Maximum number of requests that can be cached."""

    def __init__(
        self,
        *,
        api_client: RequestQueueClientAsync,
        metadata: RequestQueueMetadata,
    ) -> None:
        """Initialize a new instance.

        Preferably use the `ApifyRequestQueueClient.open` class method to create a new instance.
        """
        self._api_client = api_client
        """The Apify request queue client for API operations."""

        self._metadata = metadata
        """Additional data related to the RequestQueue."""

        self._requests_cache: LRUCache[str, Request] = LRUCache(maxsize=self._MAX_CACHED_REQUESTS)
        """A cache to store request objects. Request unique key is used as the cache key."""

        self._head_requests: deque[str] = deque()
        """Ordered unique keys of requests that that represents queue head."""

        self._requests_already_handled: set[str] = set()
        """Local estimation of requests unique keys that are already present and handled on the platform.

        (Could be persisted to optimize migrations)
        To enhance local deduplication and track handled requests to reduce amount of API calls."""

        self._requests_in_progress: set[str] = set()
        """Set of requests unique keys that are being processed locally.

        - To avoid double processing of requests that have been processing for a long time, got unlocked on the platform
           and got fetched again from platform. (Rare edge case.)
        - To help decide if the RQ is finished or not."""

        self._fetch_lock = asyncio.Lock()
        """Fetch lock to minimize race conditions when communicating with API."""


    @override
    async def get_metadata(self) -> RequestQueueMetadata:
        """Get metadata about the request queue.

        Returns:
            Metadata from the API, merged with local estimation, because in some cases, the data from the API can
            be delayed.
        """
        # TODO
        response = await self._api_client.get()
        if response is None:
            raise ValueError('Failed to fetch request queue metadata from the API.')
        # Enhance API response by local estimations (API can be delayed few seconds, while local estimation not.)
        return RequestQueueMetadata(
            id=response['id'],
            name=response['name'],
            total_request_count=max(response['totalRequestCount'], self._metadata.total_request_count),
            handled_request_count=max(response['handledRequestCount'], self._metadata.handled_request_count),
            pending_request_count=response['pendingRequestCount'],
            created_at=min(response['createdAt'], self._metadata.created_at),
            modified_at=max(response['modifiedAt'], self._metadata.modified_at),
            accessed_at=max(response['accessedAt'], self._metadata.accessed_at),
            had_multiple_clients=response['hadMultipleClients'] or self._metadata.had_multiple_clients,
        )

    @classmethod
    async def open(
        cls,
        *,
        id: str | None,
        name: str | None,
        configuration: Configuration,
    ) -> ApifyRequestQueueClient:
        """Open an Apify request queue client.

        This method creates and initializes a new instance of the Apify request queue client. It handles
        authentication, storage lookup/creation, and metadata retrieval, and sets up internal caching and queue
        management structures.

        Args:
            id: The ID of an existing request queue to open. If provided, the client will connect to this specific
                storage. Cannot be used together with `name`.
            name: The name of a request queue to get or create. If a storage with this name exists, it will be opened;
                otherwise, a new one will be created. Cannot be used together with `id`.
            configuration: The configuration object containing API credentials and settings. Must include a valid
                `token` and `api_base_url`. May also contain a `default_request_queue_id` for fallback when neither
                `id` nor `name` is provided.

        Returns:
            An instance for the opened or created storage client.

        Raises:
            ValueError: If the configuration is missing required fields (token, api_base_url), if both `id` and `name`
                are provided, or if neither `id` nor `name` is provided and no default storage ID is available
                in the configuration.
        """
        # Could be shared with the normal ApifyRequestQueueClient
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

        match (id, name):
            case (None, None):
                # If both id and name are None, try to get the default storage ID from environment variables.
                # The default storage ID environment variable is set by the Apify platform. It also contains
                # a new storage ID after Actor's reboot or migration.
                id = configuration.default_request_queue_id
            case (None, name):
                # If only name is provided, get or create the storage by name.
                id = RequestQueueMetadata.model_validate(
                    await apify_rqs_client.get_or_create(name=name),
                ).id
            case (_, None):
                # If only id is provided, use it.
                pass
            case (_, _):
                # If both id and name are provided, raise an error.
                raise ValueError('Only one of "id" or "name" can be specified, not both.')
        if id is None:
            raise RuntimeError('Unreachable code')

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
            raise ValueError(f'Opening request queue with id={id} and name={name} failed.')

        metadata_model = RequestQueueMetadata.model_validate(metadata)

        return cls(
            api_client=apify_rq_client,
            metadata=metadata_model,
        )

    @override
    async def purge(self) -> None:
        # Could be shared with the normal ApifyRequestQueueClient
        raise NotImplementedError(
            'Purging the request queue is not supported in the Apify platform. '
            'Use the `drop` method to delete the request queue instead.'
        )

    @override
    async def drop(self) -> None:
        # Could be shared with the normal ApifyRequestQueueClient
        await self._api_client.delete()

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
        # Do not try to add previously added requests to avoid pointless expensive calls to API
        # Check if request is known to be already handled (it has to be present as well.)
        # Check if request is known to be already present, but unhandled
        # Push to the platform. Probably not there, or we are not aware of it
        # (added by another producer or before migration).


        new_requests: list[ProcessedRequest] = []
        already_present_requests: list[ProcessedRequest] = []

        for request in requests:
            if request.unique_key in self._requests_already_handled:
                already_present_requests.append(
                    ProcessedRequest.model_validate(
                        {
                            'uniqueKey': request.unique_key,
                            'wasAlreadyPresent': True,
                            'wasAlreadyHandled': True,
                        }
                    )
                )
            elif self._requests_cache.get(request.unique_key):
                already_present_requests.append(
                    ProcessedRequest.model_validate(
                        {
                            'uniqueKey': request.unique_key,
                            'wasAlreadyPresent': True,
                            'wasAlreadyHandled': request.was_already_handled,
                        }
                    )
                )
            else:
                new_requests.append(
                    ProcessedRequest.model_validate(
                        {
                            'uniqueKey': request.unique_key,
                            'wasAlreadyPresent': False,
                            'wasAlreadyHandled': request.was_already_handled,
                        }
                    )
                )


                # Update local caches
                self._requests_cache[request.unique_key] = request
                if forefront:
                    self._head_requests.append(request.unique_key)
                else:
                    self._head_requests.appendleft(request.unique_key)

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
                self._requests_cache.pop(unprocessed_request.unique_key, None)

        else:
            api_response = AddRequestsResponse.model_validate(
                {'unprocessedRequests': [], 'processedRequests': already_present_requests}
            )


        # Update assumed total count for newly added requests.
        new_request_count = 0
        for processed_request in api_response.processed_requests:
            if not processed_request.was_already_present and not processed_request.was_already_handled:
                new_request_count += 1
        self._metadata.total_request_count += new_request_count

        return api_response

    @override
    async def get_request(self, unique_key: str) -> Request | None:
        """Get a request by unique key.

        Args:
            unique_key: Unique key of the request to get.

        Returns:
            The request or None if not found.
        """
        if unique_key in self._requests_cache:
            return self._requests_cache[unique_key]

        response = await self._api_client.get_request(unique_key_to_request_id(unique_key))

        if response is None:
            return None

        return Request.model_validate(response)

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
        async with self._fetch_lock:
            await self._ensure_head_is_non_empty()

            while self._head_requests:
                request_unique_key = self._head_requests.pop()
                if (
                        request_unique_key not in self._requests_in_progress and
                        request_unique_key not in self._requests_already_handled
                ):
                    self._requests_in_progress.add(request_unique_key)
                    return await self.get_request(request_unique_key)
            # No request locally and the ones returned from the platform are already in progress.
            return None

    async def _ensure_head_is_non_empty(self) -> None:
        """Ensure that the queue head has requests if they are available in the queue."""
        if len(self._head_requests)<=1:
            await self._list_head()


    async def _list_head(self) -> None:
        desired_new_head_items = 100
        # The head will contain in progress requests as well, so we need to fetch more, to get some new ones.
        requested_head_items = max(self._MAX_HEAD_ITEMS, desired_new_head_items + len(self._requests_in_progress))
        response = await self._api_client.list_head(limit=requested_head_items)

        # Update metadata
        self._queue_has_locked_requests = response.get('queueHasLockedRequests', False)
        # Check if there is another client working with the RequestQueue
        self._metadata.had_multiple_clients = response.get('hadMultipleClients', False)
        # Should warn once? This might be outside expected context if the other consumers consumes at the same time

        if modified_at := response.get('queueModifiedAt'):
            self._metadata.modified_at = max(self._metadata.modified_at, modified_at)

        # Update the cached data
        for request_data in response.get('items', []):
            request = Request.model_validate(request_data)

            if request.unique_key in self._requests_in_progress:
                # Ignore requests that are already in progress, we will not process them again.
                continue
            if request.was_already_handled:
                # Do not cache fully handled requests, we do not need them. Just cache their unique_key.
                self._requests_already_handled.add(request.unique_key)
            else:
                self._requests_cache[request.unique_key] = request
                # Add new requests to the end of the head
                self._head_requests.appendleft(request.unique_key)


    @override
    async def mark_request_as_handled(self, request: Request) -> ProcessedRequest | None:
        """Mark a request as handled after successful processing.

        Handled requests will never again be returned by the `fetch_next_request` method.

        Args:
            request: The request to mark as handled.

        Returns:
            Information about the queue operation. `None` if the given request was not in progress.
        """
        # Set the handled_at timestamp if not already set

        if request.handled_at is None:
            request.handled_at = datetime.now(tz=timezone.utc)
            self._metadata.handled_request_count += 1

        if cached_request := self._requests_cache[request.unique_key]:
            cached_request.handled_at = request.handled_at

        async with self._fetch_lock:
            try:
                # Update the request in the API
                # Works as upsert - adds the request if it does not exist yet. (Local request that was handled before
                # adding to the queue.)
                processed_request = await self._update_request(request)
                # Remove request from cache. It will most likely not be needed.
                self._requests_cache.pop(request.unique_key)
                self._requests_in_progress.discard(request.unique_key)
                # Remember that we handled this request, to optimize local deduplication.
                self._requests_already_handled.add(request.unique_key)

            except Exception as exc:
                logger.debug(f'Error marking request {request.unique_key} as handled: {exc!s}')
                return None
            else:
                return processed_request

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
        # Check if the request was marked as handled and clear it. When reclaiming,
        # we want to put the request back for processing.
        if request.was_already_handled:
            request.handled_at = None

        # Reclaim with lock to prevent race conditions that could lead to double processing of the same request.
        async with self._fetch_lock:
            try:
                # Make sure request is in the local cache. We might need it.
                self._requests_cache[request.unique_key] = request

                # No longer in progress
                self._requests_in_progress.discard(request.unique_key)
                # No longer handled
                self._requests_already_handled.discard(request.unique_key)

                if forefront:
                    # Append to top of the local head estimation
                    self._head_requests.append(request.unique_key)

                processed_request = await self._update_request(request, forefront=forefront)
                processed_request.unique_key = request.unique_key
                # If the request was previously handled, decrement our handled count since
                # we're putting it back for processing.
                if request.was_already_handled and not processed_request.was_already_handled:
                    self._metadata.handled_request_count -= 1

            except Exception as exc:
                logger.debug(f'Error reclaiming request {request.unique_key}: {exc!s}')
                return None
            else:
                return processed_request

    @override
    async def is_empty(self) -> bool:
        """Check if the queue is empty.

        Returns:
            True if the queue is empty, False otherwise.
        """
        # Without the lock the `is_empty` is prone to falsely report True with some low probability race condition.
        async with self._fetch_lock:
            await self._ensure_head_is_non_empty()
            return not self._head_requests and not self._queue_has_locked_requests and not self._requests_in_progress

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
