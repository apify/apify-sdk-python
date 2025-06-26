from __future__ import annotations

import asyncio
import os
from logging import getLogger
from typing import TYPE_CHECKING, Any

from typing_extensions import override

from apify_client import ApifyClientAsync
from apify_shared.consts import ActorEnvVars, ApifyEnvVars
from crawlee.storage_clients._base import DatasetClient
from crawlee.storage_clients.models import DatasetItemsListPage, DatasetMetadata

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from datetime import datetime

    from apify_client.clients import DatasetClientAsync
    from crawlee.configuration import Configuration

logger = getLogger(__name__)


class ApifyDatasetClient(DatasetClient):
    """An Apify platform implementation of the dataset client."""

    def __init__(
        self,
        *,
        id: str,
        name: str | None,
        created_at: datetime,
        accessed_at: datetime,
        modified_at: datetime,
        item_count: int,
        api_client: DatasetClientAsync,
    ) -> None:
        """Initialize a new instance.

        Preferably use the `ApifyDatasetClient.open` class method to create a new instance.
        """
        self._metadata = DatasetMetadata(
            id=id,
            name=name,
            created_at=created_at,
            accessed_at=accessed_at,
            modified_at=modified_at,
            item_count=item_count,
        )

        self._api_client = api_client
        """The Apify dataset client for API operations."""

        self._lock = asyncio.Lock()
        """A lock to ensure that only one operation is performed at a time."""

    @property
    @override
    def metadata(self) -> DatasetMetadata:
        return self._metadata

    @override
    @classmethod
    async def open(
        cls,
        *,
        id: str | None,
        name: str | None,
        configuration: Configuration,
    ) -> ApifyDatasetClient:
        token = getattr(configuration, 'token', None)
        if not token:
            raise ValueError(f'Apify storage client requires a valid token in Configuration (token={token}).')

        api_url = getattr(configuration, 'api_base_url', None)
        if not api_url:
            raise ValueError(f'Apify storage client requires a valid API URL in Configuration (api_url={api_url}).')

        # Otherwise, create a new one.
        apify_client_async = ApifyClientAsync(
            token=token,
            api_url=api_url,
            max_retries=8,
            min_delay_between_retries_millis=500,
            timeout_secs=360,
        )

        apify_datasets_client = apify_client_async.datasets()

        if id and name:
            raise ValueError('Only one of "id" or "name" can be specified, not both.')

        # If name is provided, get or create the storage by name.
        if name is not None and id is None:
            id = DatasetMetadata.model_validate(
                await apify_datasets_client.get_or_create(name=name),
            ).id

        # If both id and name are None, try to get the default storage ID from environment variables.
        if id is None and name is None:
            id = os.environ.get(
                ActorEnvVars.DEFAULT_DATASET_ID.value,
                None,
            ) or os.environ.get(
                ApifyEnvVars.DEFAULT_DATASET_ID.value,
                None,
            )

        if id is None:
            raise ValueError(
                'Either "id" or "name" must be provided, or the storage ID must be set in environment variable.'
            )

        # Get the client for the specific storage by ID.
        apify_dataset_client = apify_client_async.dataset(dataset_id=id)

        # Fetch its metadata.
        metadata = DatasetMetadata.model_validate(await apify_dataset_client.get())

        return cls(
            id=metadata.id,
            name=metadata.name,
            created_at=metadata.created_at,
            accessed_at=metadata.accessed_at,
            modified_at=metadata.modified_at,
            item_count=metadata.item_count,
            api_client=apify_dataset_client,
        )

    @override
    async def purge(self) -> None:
        raise NotImplementedError(
            'Purging datasets is not supported in the Apify platform. '
            'Use the `drop` method to delete the dataset instead.'
        )

    @override
    async def drop(self) -> None:
        async with self._lock:
            await self._api_client.delete()

    @override
    async def push_data(self, data: list[Any] | dict[str, Any]) -> None:
        async with self._lock:
            await self._api_client.push_items(items=data)
            await self._update_metadata()

    @override
    async def get_data(
        self,
        *,
        offset: int = 0,
        limit: int | None = 999_999_999_999,
        clean: bool = False,
        desc: bool = False,
        fields: list[str] | None = None,
        omit: list[str] | None = None,
        unwind: str | None = None,
        skip_empty: bool = False,
        skip_hidden: bool = False,
        flatten: list[str] | None = None,
        view: str | None = None,
    ) -> DatasetItemsListPage:
        response = await self._api_client.list_items(
            offset=offset,
            limit=limit,
            clean=clean,
            desc=desc,
            fields=fields,
            omit=omit,
            unwind=unwind,
            skip_empty=skip_empty,
            skip_hidden=skip_hidden,
            flatten=flatten,
            view=view,
        )
        result = DatasetItemsListPage.model_validate(vars(response))
        await self._update_metadata()
        return result

    @override
    async def iterate_items(
        self,
        *,
        offset: int = 0,
        limit: int | None = None,
        clean: bool = False,
        desc: bool = False,
        fields: list[str] | None = None,
        omit: list[str] | None = None,
        unwind: str | None = None,
        skip_empty: bool = False,
        skip_hidden: bool = False,
    ) -> AsyncIterator[dict]:
        async for item in self._api_client.iterate_items(
            offset=offset,
            limit=limit,
            clean=clean,
            desc=desc,
            fields=fields,
            omit=omit,
            unwind=unwind,
            skip_empty=skip_empty,
            skip_hidden=skip_hidden,
        ):
            yield item

        await self._update_metadata()

    async def _update_metadata(self) -> None:
        """Update the dataset metadata file with current information."""
        metadata = await self._api_client.get()
        self._metadata = DatasetMetadata.model_validate(metadata)
