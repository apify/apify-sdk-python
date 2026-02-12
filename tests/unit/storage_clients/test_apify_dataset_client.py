from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from apify.storage_clients._apify._dataset_client import ApifyDatasetClient


def _make_dataset_client() -> ApifyDatasetClient:
    """Create an ApifyDatasetClient with a mocked API client."""
    api_client = AsyncMock()
    return ApifyDatasetClient(api_client=api_client, api_public_base_url='', lock=asyncio.Lock())


async def test_purge_raises_not_implemented() -> None:
    """Test that purge() raises NotImplementedError."""
    client = _make_dataset_client()
    with pytest.raises(NotImplementedError, match='Purging datasets is not supported'):
        await client.purge()


async def test_drop_calls_api_delete() -> None:
    """Test that drop() delegates to the API client."""
    client = _make_dataset_client()
    await client.drop()
    client._api_client.delete.assert_awaited_once()  # ty: ignore[possibly-missing-attribute]


async def test_deprecated_api_public_base_url() -> None:
    """Test that passing api_public_base_url triggers deprecation warning."""
    api_client = AsyncMock()
    with pytest.warns(DeprecationWarning, match='api_public_base_url argument is deprecated'):
        ApifyDatasetClient(
            api_client=api_client,
            api_public_base_url='https://api.apify.com',
            lock=asyncio.Lock(),
        )
