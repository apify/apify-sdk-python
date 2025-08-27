from __future__ import annotations

import re
from base64 import b64encode
from hashlib import sha256
from logging import getLogger
from typing import TYPE_CHECKING, Final

from typing_extensions import override

from apify_client import ApifyClientAsync
from crawlee._utils.crypto import crypto_random_object_id
from crawlee.storage_clients._base import RequestQueueClient
from crawlee.storage_clients.models import RequestQueueMetadata

if TYPE_CHECKING:
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
    """Base class for Apify platform implementations of the request queue client."""

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
