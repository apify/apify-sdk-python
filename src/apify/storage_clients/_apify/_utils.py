from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING, Literal

from apify_client import ApifyClientAsync

if TYPE_CHECKING:
    from apify_client.clients import KeyValueStoreClientAsync

    from apify import Configuration

logger = getLogger(__name__)


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

    # Create the key for this alias
    alias_key = f'alias-{storage_type}-{alias}'

    # Try to get the stored ID for this alias
    try:
        record = await default_kvs_client.get_record(alias_key)
        if record and record.get('value'):
            # The record structure is: {'value': {'value': 'storage_id'}}
            value_data = record['value']
            if isinstance(value_data, dict) and 'value' in value_data:
                storage_id = value_data['value']
                if isinstance(storage_id, str):
                    return storage_id
    except Exception as e:
        # If there's any error accessing the record, treat it as not found
        logger.warning(f'Error accessing alias mapping for {alias}: {e}')

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

    # Create the key for this alias (must match the format in resolve_alias_to_id)
    alias_key = f'alias-{storage_type}-{alias}'

    # Store the mapping
    await default_kvs_client.set_record(alias_key, {'value': storage_id})


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
