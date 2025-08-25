from __future__ import annotations

import asyncio
import re
from base64 import b64encode
from collections import deque
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from logging import getLogger
from typing import TYPE_CHECKING, Final

from cachetools import LRUCache
from typing_extensions import override

from apify_client import ApifyClientAsync
from crawlee._utils.crypto import crypto_random_object_id
from crawlee.storage_clients._base import RequestQueueClient
from crawlee.storage_clients.models import AddRequestsResponse, ProcessedRequest, RequestQueueMetadata

from ._models import CachedRequest, ProlongRequestLockResponse, RequestQueueHead
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
    """An Apify platform implementation of the request queue client."""

    _DEFAULT_LOCK_TIME: Final[timedelta] = timedelta(minutes=3)
    """The default lock time for requests in the queue."""

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

        self._queue_head = deque[str]()
        """A deque to store request unique keys in the queue head."""

        self._requests_cache: LRUCache[str, CachedRequest] = LRUCache(maxsize=self._MAX_CACHED_REQUESTS)
        """A cache to store request objects. Request unique key is used as the cache key."""

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
        if self._metadata.had_multiple_clients:
            return await self.get_metadata()
        # Get local estimation (will not include changes done bo another client)
        return self._metadata

    @override
    async def get_metadata(self) -> RequestQueueMetadata:
        """Get metadata about the request queue.

        Returns:
            Metadata from the API, merged with local estimation, because in some cases, the data from the API can
            be delayed.
        """
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
            if self._requests_cache.get(request.unique_key):
                # We are not sure if it was already handled at this point, and it is not worth calling API for it.
                # It could have been handled by another client in the meantime, so cached information about
                # `request.was_already_handled` is not reliable.
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
                # Add new request to the cache.
                processed_request = ProcessedRequest.model_validate(
                    {
                        'uniqueKey': request.unique_key,
                        'wasAlreadyPresent': True,
                        'wasAlreadyHandled': request.was_already_handled,
                    }
                )
                self._cache_request(
                    request.unique_key,
                    processed_request,
                )
                new_requests.append(request)

        if new_requests:
            # Prepare requests for API by converting to dictionaries.
            requests_dict = [
                request.model_dump(
                    by_alias=True,
                    exclude={'id'},  # Exclude ID fields from requests since the API doesn't accept them.
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

        return api_response

    @override
    async def get_request(self, unique_key: str) -> Request | None:
        """Get a request by unique key.

        Args:
            unique_key: Unique key of the request to get.

        Returns:
            The request or None if not found.
        """
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
        # Ensure the queue head has requests if available. Fetching the head with lock to prevent race conditions.
        async with self._fetch_lock:
            await self._ensure_head_is_non_empty()

            # If queue head is empty after ensuring, there are no requests
            if not self._queue_head:
                return None

            # Get the next request ID from the queue head
            next_unique_key = self._queue_head.popleft()

        request = await self._get_or_hydrate_request(next_unique_key)

        # Handle potential inconsistency where request might not be in the main table yet
        if request is None:
            logger.debug(
                'Cannot find a request from the beginning of queue, will be retried later',
                extra={'nextRequestUniqueKey': next_unique_key},
            )
            return None

        # If the request was already handled, skip it
        if request.handled_at is not None:
            logger.debug(
                'Request fetched from the beginning of queue was already handled',
                extra={'nextRequestUniqueKey': next_unique_key},
            )
            return None

        # Use get request to ensure we have the full request object.
        request = await self.get_request(request.unique_key)
        if request is None:
            logger.debug(
                'Request fetched from the beginning of queue was not found in the RQ',
                extra={'nextRequestUniqueKey': next_unique_key},
            )
            return None

        return request

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

        if cached_request := self._requests_cache[request.unique_key]:
            cached_request.was_already_handled = request.was_already_handled
        try:
            # Update the request in the API
            processed_request = await self._update_request(request)
            processed_request.unique_key = request.unique_key

            # Update assumed handled count if this wasn't already handled
            if not processed_request.was_already_handled:
                self._metadata.handled_request_count += 1

            # Update the cache with the handled request
            cache_key = request.unique_key
            self._cache_request(
                cache_key,
                processed_request,
                hydrated_request=request,
            )
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
                # Update the request in the API.
                processed_request = await self._update_request(request, forefront=forefront)
                processed_request.unique_key = request.unique_key

                # If the request was previously handled, decrement our handled count since
                # we're putting it back for processing.
                if request.was_already_handled and not processed_request.was_already_handled:
                    self._metadata.handled_request_count -= 1

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

                # Try to release the lock on the request
                try:
                    await self._delete_request_lock(request.unique_key, forefront=forefront)
                except Exception as err:
                    logger.debug(f'Failed to delete request lock for request {request.unique_key}', exc_info=err)
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
        # Check _list_head and self._queue_has_locked_requests with lock to make sure they are consistent.
        # Without the lock the `is_empty` is prone to falsely report True with some low probability race condition.
        async with self._fetch_lock:
            head = await self._list_head(limit=1, lock_time=None)
            return len(head.items) == 0 and not self._queue_has_locked_requests

    async def _ensure_head_is_non_empty(self) -> None:
        """Ensure that the queue head has requests if they are available in the queue."""
        # If queue head has adequate requests, skip fetching more
        if len(self._queue_head) > 1 and not self._should_check_for_forefront_requests:
            return

        # Fetch requests from the API and populate the queue head
        await self._list_head(lock_time=self._DEFAULT_LOCK_TIME)

    async def _get_or_hydrate_request(self, unique_key: str) -> Request | None:
        """Get a request by unique key, either from cache or by fetching from API.

        Args:
            unique_key: Unique key of the request to get.

        Returns:
            The request if found and valid, otherwise None.
        """
        # First check if the request is in our cache
        cached_entry = self._requests_cache.get(unique_key)

        if cached_entry and cached_entry.hydrated:
            # If we have the request hydrated in cache, check if lock is expired
            if cached_entry.lock_expires_at and cached_entry.lock_expires_at < datetime.now(tz=timezone.utc):
                # Try to prolong the lock if it's expired
                try:
                    lock_secs = int(self._DEFAULT_LOCK_TIME.total_seconds())
                    response = await self._prolong_request_lock(unique_key, lock_secs=lock_secs)
                    cached_entry.lock_expires_at = response.lock_expires_at
                except Exception:
                    # If prolonging the lock fails, we lost the request
                    logger.debug(f'Failed to prolong lock for request {unique_key}, returning None')
                    return None

            return cached_entry.hydrated

        # If not in cache or not hydrated, fetch the request
        try:
            # Try to acquire or prolong the lock
            lock_secs = int(self._DEFAULT_LOCK_TIME.total_seconds())
            await self._prolong_request_lock(unique_key, lock_secs=lock_secs)

            # Fetch the request data
            request = await self.get_request(unique_key)

            # If request is not found, release lock and return None
            if not request:
                await self._delete_request_lock(unique_key)
                return None

            # Update cache with hydrated request
            cache_key = request.unique_key
            self._cache_request(
                cache_key,
                ProcessedRequest(
                    unique_key=request.unique_key,
                    was_already_present=True,
                    was_already_handled=request.handled_at is not None,
                ),
                hydrated_request=request,
            )
        except Exception as exc:
            logger.debug(f'Error fetching or locking request {unique_key}: {exc!s}')
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
        lock_time: timedelta | None = None,
        limit: int = 25,
    ) -> RequestQueueHead:
        """Retrieve requests from the beginning of the queue.

        Args:
            lock_time: Duration for which to lock the retrieved requests.
                If None, requests will not be locked.
            limit: Maximum number of requests to retrieve.

        Returns:
            A collection of requests from the beginning of the queue.
        """
        # Return from cache if available and we're not checking for new forefront requests
        if self._queue_head and not self._should_check_for_forefront_requests:
            logger.debug(f'Using cached queue head with {len(self._queue_head)} requests')
            # Create a list of requests from the cached queue head
            items = []
            for unique_key in list(self._queue_head)[:limit]:
                cached_request = self._requests_cache.get(unique_key)
                if cached_request and cached_request.hydrated:
                    items.append(cached_request.hydrated)

            metadata = await self._get_metadata_estimate()

            return RequestQueueHead(
                limit=limit,
                had_multiple_clients=metadata.had_multiple_clients,
                queue_modified_at=metadata.modified_at,
                items=items,
                queue_has_locked_requests=self._queue_has_locked_requests,
                lock_time=lock_time,
            )
        leftover_buffer = list[str]()
        if self._should_check_for_forefront_requests:
            leftover_buffer = list(self._queue_head)
            self._queue_head.clear()
            self._should_check_for_forefront_requests = False

        # Otherwise fetch from API
        lock_time = lock_time or self._DEFAULT_LOCK_TIME
        lock_secs = int(lock_time.total_seconds())

        response = await self._api_client.list_and_lock_head(
            lock_secs=lock_secs,
            limit=limit,
        )

        # Update the queue head cache
        self._queue_has_locked_requests = response.get('queueHasLockedRequests', False)
        # Check if there is another client working with the RequestQueue
        self._metadata.had_multiple_clients = response.get('hadMultipleClients', False)

        for request_data in response.get('items', []):
            request = Request.model_validate(request_data)

            # Skip requests without ID or unique key
            if not request.unique_key:
                logger.debug(
                    'Skipping request from queue head, missing ID or unique key',
                    extra={
                        'unique_key': request.unique_key,
                    },
                )
                continue

            # Cache the request
            self._cache_request(
                request.unique_key,
                ProcessedRequest(
                    unique_key=request.unique_key,
                    was_already_present=True,
                    was_already_handled=False,
                ),
                hydrated_request=request,
            )
            self._queue_head.append(request.unique_key)

        for leftover_unique_key in leftover_buffer:
            # After adding new requests to the forefront, any existing leftover locked request is kept in the end.
            self._queue_head.append(leftover_unique_key)
        return RequestQueueHead.model_validate(response)

    async def _prolong_request_lock(
        self,
        unique_key: str,
        *,
        lock_secs: int,
    ) -> ProlongRequestLockResponse:
        """Prolong the lock on a specific request in the queue.

        Args:
            unique_key: Unique key of the request whose lock is to be prolonged.
            lock_secs: The additional amount of time, in seconds, that the request will remain locked.

        Returns:
            A response containing the time at which the lock will expire.
        """
        response = await self._api_client.prolong_request_lock(
            request_id=unique_key_to_request_id(unique_key),
            # All requests reaching this code were the tip of the queue at the moment when they were fetched,
            # so if their lock expires, they should be put back to the forefront as their handling is long overdue.
            forefront=True,
            lock_secs=lock_secs,
        )

        result = ProlongRequestLockResponse(
            lock_expires_at=datetime.fromisoformat(response['lockExpiresAt'].replace('Z', '+00:00'))
        )

        # Update the cache with the new lock expiration
        for cached_request in self._requests_cache.values():
            if cached_request.unique_key == unique_key:
                cached_request.lock_expires_at = result.lock_expires_at
                break

        return result

    async def _delete_request_lock(
        self,
        unique_key: str,
        *,
        forefront: bool = False,
    ) -> None:
        """Delete the lock on a specific request in the queue.

        Args:
            unique_key: Unique key of the request to delete the lock.
            forefront: Whether to put the request in the beginning or the end of the queue after the lock is deleted.
        """
        try:
            await self._api_client.delete_request_lock(
                request_id=unique_key_to_request_id(unique_key),
                forefront=forefront,
            )

            # Update the cache to remove the lock
            for cached_request in self._requests_cache.values():
                if cached_request.unique_key == unique_key:
                    cached_request.lock_expires_at = None
                    break
        except Exception as err:
            logger.debug(f'Failed to delete request lock for request {unique_key}', exc_info=err)

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
            unique_key=processed_request.unique_key,
            was_already_handled=processed_request.was_already_handled,
            hydrated=hydrated_request,
            lock_expires_at=None,
        )
