from __future__ import annotations

import pytest

from apify._configuration import Configuration
from apify.storage_clients._apify._api_client_creation import _create_api_client, create_storage_api_client


def test_create_api_client_without_token() -> None:
    """Test that _create_api_client raises ValueError when no token is set."""
    config = Configuration(token=None)
    with pytest.raises(ValueError, match='requires a valid token'):
        _create_api_client(config)


def test_create_api_client_without_api_url() -> None:
    """Test that _create_api_client raises ValueError when API URL is empty."""
    config = Configuration(token='test-token')
    # Force the api_base_url to be empty
    object.__setattr__(config, 'api_base_url', '')
    with pytest.raises(ValueError, match='requires a valid API URL'):
        _create_api_client(config)


def test_create_api_client_without_public_api_url() -> None:
    """Test that _create_api_client raises ValueError when public API URL is empty."""
    config = Configuration(token='test-token')
    object.__setattr__(config, 'api_public_base_url', '')
    with pytest.raises(ValueError, match='requires a valid API public base URL'):
        _create_api_client(config)


async def test_create_storage_multiple_identifiers() -> None:
    """Test that create_storage_api_client raises ValueError for multiple identifiers."""
    config = Configuration(token='test-token')
    with pytest.raises(ValueError, match='Only one of'):
        await create_storage_api_client(
            storage_type='Dataset',
            configuration=config,
            id='some-id',
            name='some-name',
        )


async def test_create_storage_unknown_type() -> None:
    """Test that create_storage_api_client raises ValueError for unknown storage type."""
    config = Configuration(token='test-token')
    with pytest.raises(ValueError, match='Unknown storage type'):
        await create_storage_api_client(  # ty: ignore[no-matching-overload]
            storage_type='UnknownType',
            configuration=config,
        )
