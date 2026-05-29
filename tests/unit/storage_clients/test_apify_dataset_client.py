from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from apify.storage_clients._apify._dataset_client import ApifyDatasetClient


def _make_dataset_client(api_client: AsyncMock | None = None) -> tuple[ApifyDatasetClient, AsyncMock]:
    """Create an ApifyDatasetClient with a mocked API client."""
    if api_client is None:
        api_client = AsyncMock()

    return ApifyDatasetClient(
        api_client=api_client,
        lock=asyncio.Lock(),
    ), api_client


async def test_purge_raises_not_implemented() -> None:
    """Test that purge() raises NotImplementedError."""
    client, _ = _make_dataset_client()
    with pytest.raises(NotImplementedError, match='Purging datasets is not supported'):
        await client.purge()


async def test_drop_calls_api_delete() -> None:
    """Test that drop() delegates to the API client."""
    client, api_client = _make_dataset_client()
    await client.drop()
    api_client.delete.assert_awaited_once()
