from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING, Literal

from apify_client import ApifyClientAsync

if TYPE_CHECKING:
    from apify_client.clients import KeyValueStoreClientAsync

    from apify import Configuration

logger = getLogger(__name__)

_ALIAS_MAPPING_KEY = '__STORAGE_ALIASES_MAPPING'


async def resolve_alias_to_id(
    alias: str,
    storage_type: Literal['dataset', 'kvs', 'rq'],
    configuration: Configuration,
) -> str | None:
    """Resolve a storage alias to its corresponding storage ID.

    Args:
        alias: The alias to resolve.
        storage_type: Type of storage ('dataset', 'key_value_store', or 'request_queue').
        configuration: The configuration object containing API credentials.

    Returns:
        The storage ID if found, None if the alias doesn't exist.
    """
    default_kvs_client = await _get_default_kvs_client(configuration)

    # Create the dictionary key for this alias.
    alias_key = f'alias-{storage_type}-{alias}'

    try:
        record = await default_kvs_client.get_record(_ALIAS_MAPPING_KEY)

        # get_record can return {key: ..., value: ..., content_type: ...}
        if isinstance(record, dict) and 'value' in record:
            record = record['value']

        # Extract the actual data from the KVS record
        if isinstance(record, dict) and alias_key in record:
            storage_id = record[alias_key]
            return str(storage_id)

    except Exception as exc:
        # If there's any error accessing the record, treat it as not found.
        logger.warning(f'Error accessing alias mapping for {alias}: {exc}')

    return None


async def store_alias_mapping(
    alias: str,
    storage_type: Literal['dataset', 'kvs', 'rq'],
    storage_id: str,
    configuration: Configuration,
) -> None:
    """Store a mapping from alias to storage ID in the default key-value store.

    Args:
        alias: The alias to store.
        storage_type: Type of storage ('dataset', 'key_value_store', or 'request_queue').
        storage_id: The storage ID to map the alias to.
        configuration: The configuration object containing API credentials.
    """
    default_kvs_client = await _get_default_kvs_client(configuration)

    # Create the dictionary key for this alias.
    alias_key = f'alias-{storage_type}-{alias}'

    try:
        record = await default_kvs_client.get_record(_ALIAS_MAPPING_KEY)

        # get_record can return {key: ..., value: ..., content_type: ...}
        if isinstance(record, dict) and 'value' in record:
            record = record['value']

        # Update or create the record with the new alias mapping
        if isinstance(record, dict):
            record[alias_key] = storage_id
        else:
            record = {alias_key: storage_id}

        # Store the mapping back in the KVS.
        await default_kvs_client.set_record(_ALIAS_MAPPING_KEY, record)
    except Exception as exc:
        logger.warning(f'Error accessing alias mapping for {alias}: {exc}')


async def _get_default_kvs_client(configuration: Configuration) -> KeyValueStoreClientAsync:
    """Get a client for the default key-value store."""
    token = configuration.token
    if not token:
        raise ValueError(f'Apify storage client requires a valid token in Configuration (token={token}).')

    api_url = configuration.api_base_url
    if not api_url:
        raise ValueError(f'Apify storage client requires a valid API URL in Configuration (api_url={api_url}).')

    # Create Apify client with the provided token and API URL
    apify_client_async = ApifyClientAsync(
        token=token,
        api_url=api_url,
        max_retries=8,
        min_delay_between_retries_millis=500,
        timeout_secs=360,
    )

    # Get the default key-value store ID from configuration
    default_kvs_id = configuration.default_key_value_store_id

    return apify_client_async.key_value_store(key_value_store_id=default_kvs_id)
