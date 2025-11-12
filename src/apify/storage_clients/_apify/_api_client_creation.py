from __future__ import annotations

from typing import TYPE_CHECKING, Literal, overload

from apify_client import ApifyClientAsync
from crawlee._utils.crypto import crypto_random_object_id

from apify.storage_clients._apify._alias_resolving import open_by_alias

if TYPE_CHECKING:
    from apify_client.clients import DatasetClientAsync, KeyValueStoreClientAsync, RequestQueueClientAsync

    from apify._configuration import Configuration


@overload
async def create_storage_api_client(
    *,
    storage_type: Literal['Dataset'],
    configuration: Configuration,
    id: str | None = None,
    name: str | None = None,
    alias: str | None = None,
) -> DatasetClientAsync: ...


@overload
async def create_storage_api_client(
    *,
    storage_type: Literal['KeyValueStore'],
    configuration: Configuration,
    id: str | None = None,
    name: str | None = None,
    alias: str | None = None,
) -> KeyValueStoreClientAsync: ...


@overload
async def create_storage_api_client(
    *,
    storage_type: Literal['RequestQueue'],
    configuration: Configuration,
    id: str | None = None,
    name: str | None = None,
    alias: str | None = None,
) -> RequestQueueClientAsync: ...


async def create_storage_api_client(
    *,
    storage_type: Literal['Dataset', 'KeyValueStore', 'RequestQueue'],
    configuration: Configuration,
    id: str | None = None,
    name: str | None = None,
    alias: str | None = None,
) -> KeyValueStoreClientAsync | RequestQueueClientAsync | DatasetClientAsync:
    """Get an Apify API client for a specific storage type.

    This function handles the creation and initialization of Apify storage clients (KVS, RQ, or Dataset).
    It manages authentication, storage lookup/creation, and client instantiation.

    Args:
        storage_type: The type of storage to open.
        configuration: Configuration object containing API credentials.
        id: Storage ID to open. Mutually exclusive with name and alias.
        name: Storage name (global scope, persists across runs). Mutually exclusive with id and alias.
        alias: Storage alias (run scope, creates unnamed storage). Mutually exclusive with id and name.

    Returns:
        The storage client for the opened or created storage.

    Raises:
        ValueError: If configuration is invalid, multiple identifiers are provided, or storage cannot be found.
    """
    if sum(1 for param in [id, name, alias] if param is not None) > 1:
        raise ValueError('Only one of "id", "name", or "alias" can be specified, not multiple.')

    apify_client = _create_api_client(configuration)

    # Get storage-specific configuration
    if storage_type == 'KeyValueStore':
        collection_client = apify_client.key_value_stores()
        default_id = configuration.default_key_value_store_id

        def get_resource_client(storage_id: str) -> KeyValueStoreClientAsync:
            return apify_client.key_value_store(key_value_store_id=storage_id)

    elif storage_type == 'RequestQueue':
        collection_client = apify_client.request_queues()  # type: ignore[assignment]
        default_id = configuration.default_request_queue_id

        def get_resource_client(storage_id: str) -> RequestQueueClientAsync:  # type: ignore[misc]
            # Use suitable client_key to make `hadMultipleClients` response of Apify API useful.
            # It should persist across migrated or resurrected Actor runs on the Apify platform.
            _api_max_client_key_length = 32
            client_key = (configuration.actor_run_id or crypto_random_object_id(length=_api_max_client_key_length))[
                :_api_max_client_key_length
            ]
            return apify_client.request_queue(request_queue_id=storage_id, client_key=client_key)

    elif storage_type == 'Dataset':
        collection_client = apify_client.datasets()  # type: ignore[assignment]
        default_id = configuration.default_dataset_id

        def get_resource_client(storage_id: str) -> DatasetClientAsync:  # type: ignore[misc]
            return apify_client.dataset(dataset_id=storage_id)

    else:
        raise ValueError(f'Unknown storage type: {storage_type}')

    # Handle different opening scenarios
    match (alias, name, id, default_id):
        # Normalize unnamed default storage to unnamed storage aliased as `__default__`.
        case (None, None, None, None):
            return await open_by_alias(
                alias='__default__',
                storage_type=storage_type,  # type: ignore[arg-type]
                collection_client=collection_client,
                get_resource_client_by_id=get_resource_client,
                configuration=configuration,
            )

        # Open by alias.
        case (str(), None, None, _):
            return await open_by_alias(
                alias=alias,
                storage_type=storage_type,  # type: ignore[arg-type]
                collection_client=collection_client,
                get_resource_client_by_id=get_resource_client,
                configuration=configuration,
            )

        # Open default storage.
        case (None, None, None, str()):
            resource_client = get_resource_client(default_id)
            raw_metadata = await resource_client.get()
            # Default storage does not exist. Create a new one.
            if not raw_metadata:
                raw_metadata = await collection_client.get_or_create()
                resource_client = get_resource_client(raw_metadata['id'])
            return resource_client

        # Open by name.
        case (None, str(), None, _):
            raw_metadata = await collection_client.get_or_create(name=name)
            return get_resource_client(raw_metadata['id'])

        # Open by ID.
        case (None, None, str(), _):
            resource_client = get_resource_client(id)
            raw_metadata = await resource_client.get()
            if raw_metadata is None:
                raise ValueError(f'Opening {storage_type} with id={id} failed.')
            return resource_client

    raise RuntimeError('Unreachable code')


def _create_api_client(configuration: Configuration) -> ApifyClientAsync:
    """Create and validate an ApifyClientAsync from the given Configuration."""
    if not configuration.token:
        raise ValueError(f'Apify storage client requires a valid token in Configuration (token={configuration.token}).')

    if not configuration.api_base_url:
        raise ValueError(
            f'Apify storage client requires a valid API URL in Configuration (api_url={configuration.api_base_url}).'
        )

    if not configuration.api_public_base_url:
        raise ValueError(
            'Apify storage client requires a valid API public base URL in Configuration '
            f'(api_public_base_url={configuration.api_public_base_url}).'
        )

    return ApifyClientAsync(
        token=configuration.token,
        api_url=configuration.api_base_url,
        api_public_url=configuration.api_public_base_url,
        max_retries=8,
        min_delay_between_retries_millis=500,
        timeout_secs=360,
    )
