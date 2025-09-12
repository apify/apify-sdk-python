"""Utility functions for handling storage aliases."""

from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from apify_client import ApifyClientAsync

if TYPE_CHECKING:
    from apify_client.clients import KeyValueStoreClientAsync

    from apify import Configuration

logger = getLogger(__name__)


async def resolve_alias_to_id(
    alias: str,
    storage_type: str,
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
    # Get the default key-value store to check for alias mappings
    default_kvs_client = await _get_default_kvs_client(configuration)

    # Create the key for this alias
    alias_key = f'alias:{storage_type}:{alias}'

    # Try to get the stored ID for this alias
    try:
        record = await default_kvs_client.get_record(alias_key)
        if record and record.get('value'):
            storage_id = record['value']
            if isinstance(storage_id, str):
                logger.debug(f'Found existing alias mapping: {alias} -> {storage_id}')
                return storage_id
    except Exception:
        # If there's any error accessing the record, treat it as not found
        logger.debug(f'No existing alias mapping found for {alias}')

    return None
async def store_alias_mapping(
    alias: str,
    storage_type: str,
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
    # Get the default key-value store to store alias mappings
    default_kvs_client = await _get_default_kvs_client(configuration)

    # Create the key for this alias
    alias_key = f'alias-{storage_type}-{alias}'

    # Store the mapping
    await default_kvs_client.set_record(alias_key, {'value': storage_id})
    logger.debug(f'Stored alias mapping: {alias} -> {storage_id}')


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


def validate_storage_parameters(id: str | None, name: str | None, alias: str | None) -> None:
    """Validate that only one of id, name, or alias is provided.

    Args:
        id: The storage ID.
        name: The storage name.
        alias: The storage alias.

    Raises:
        ValueError: If more than one parameter is provided or if name and alias are both provided.
    """
    provided_params = sum(1 for param in [id, name, alias] if param is not None)

    if provided_params > 1:
        raise ValueError('Only one of "id", "name", or "alias" can be specified.')

    # Additional check for mutual exclusivity of name and alias as mentioned in Actor docstrings
    if name is not None and alias is not None:
        raise ValueError('Parameters "name" and "alias" are mutually exclusive.')
