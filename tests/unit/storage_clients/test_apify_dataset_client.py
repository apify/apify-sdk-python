from __future__ import annotations

import asyncio
from typing import Any
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


async def test_concurrent_push_data_overlaps() -> None:
    """Concurrent pushes reach the API at the same time instead of queueing behind each other."""
    concurrency = 3
    barrier = asyncio.Barrier(concurrency)
    api_client = AsyncMock()

    async def push_items(**_kwargs: Any) -> None:
        # Every concurrent push must reach the API call before any of them is allowed to return.
        await barrier.wait()

    api_client.push_items = push_items
    client, _ = _make_dataset_client(api_client)

    async with asyncio.timeout(5):
        await asyncio.gather(*(client.push_data({'id': i}) for i in range(concurrency)))
