from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from apify_shared.consts import ApifyEnvVars

from ._utils import generate_unique_resource_name
from apify import Actor
from apify.storage_clients import ApifyStorageClient
from apify.storages import Dataset

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from apify_client import ApifyClientAsync


@pytest.fixture
async def dataset_apify(apify_token: str, monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[Dataset]:
    """Create an instance of the Apify dataset on the platform and drop it when the test is finished."""
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_token)

    async with Actor:
        ds = await Dataset.open(storage_client=ApifyStorageClient())
        yield ds
        await ds.drop()


async def test_push_and_verify_data_in_default_dataset(dataset_apify: Dataset) -> None:
    """Test pushing 100 items and verifying them via API."""
    desired_item_count = 100
    ds = dataset_apify

    await ds.push_data([{'id': i} for i in range(desired_item_count)])

    items = await ds.list_items()
    assert len(items) == desired_item_count
    assert items[0]['id'] == 0
    assert items[-1]['id'] == desired_item_count - 1


async def test_push_large_data_chunks_over_9mb(dataset_apify: Dataset) -> None:
    """Test that SDK chunking logic works for large payloads."""
    ds = dataset_apify

    await ds.push_data([{'str': 'x' * 10000} for _ in range(5000)])  # ~50MB

    items = await ds.list_items()
    assert len(items) == 5000
    for item in items:
        assert item['str'] == 'x' * 10000


async def test_dataset_iter_items(dataset_apify: Dataset) -> None:
    """Test iteration over dataset items."""
    inserted_data = {'Something': 'something else'}
    ds = dataset_apify

    await ds.push_data(inserted_data)
    requested_data = [item async for item in ds.iterate_items()]

    assert len(requested_data) == 1
    assert requested_data[0] == inserted_data


async def test_same_references_in_default_dataset(apify_token: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that opening the default dataset twice returns the same instance."""
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_token)

    async with Actor:
        dataset1 = await Actor.open_dataset()
        dataset2 = await Actor.open_dataset()
        assert dataset1 is dataset2


async def test_same_references_in_named_dataset(apify_token: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that opening a named dataset by name and then by ID returns the same instance."""
    dataset_name = generate_unique_resource_name('dataset')
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_token)

    async with Actor:
        dataset_by_name_1 = await Actor.open_dataset(name=dataset_name)
        try:
            dataset_by_name_2 = await Actor.open_dataset(name=dataset_name)
            assert dataset_by_name_1 is dataset_by_name_2

            dataset_1_metadata = await dataset_by_name_1.get_metadata()
            dataset_by_id_1 = await Actor.open_dataset(id=dataset_1_metadata.id)
            dataset_by_id_2 = await Actor.open_dataset(id=dataset_1_metadata.id)
            assert dataset_by_id_1 is dataset_by_name_1
            assert dataset_by_id_2 is dataset_by_id_1
        finally:
            await dataset_by_name_1.drop()


async def test_force_cloud(
    apify_client_async: ApifyClientAsync,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that force_cloud creates storage in the cloud even when running locally."""
    assert apify_client_async.token is not None
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_client_async.token)

    dataset_name = generate_unique_resource_name('dataset')
    dataset_item = {'foo': 'bar'}

    async with Actor:
        dataset = await Actor.open_dataset(name=dataset_name, force_cloud=True)
        dataset_id = (await dataset.get_metadata()).id

        await dataset.push_data(dataset_item)

    dataset_client = apify_client_async.dataset(dataset_id)

    try:
        dataset_details = await dataset_client.get()
        assert dataset_details is not None
        assert dataset_details.get('name') == dataset_name

        dataset_items = await dataset_client.list_items()
        assert dataset_items.items == [dataset_item]
    finally:
        await dataset_client.delete()
