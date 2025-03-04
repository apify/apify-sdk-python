from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from crawlee.storage_clients._base import DatasetCollectionClient as BaseDatasetCollectionClient
from crawlee.storage_clients.models import DatasetListPage, DatasetMetadata

if TYPE_CHECKING:
    from apify_client.clients import DatasetCollectionClientAsync


class DatasetCollectionClient(BaseDatasetCollectionClient):
    """Dataset collection resource client implementation based on the Apify platform storage."""

    def __init__(self, apify_dataset_collection_client: DatasetCollectionClientAsync) -> None:
        self._client = apify_dataset_collection_client

    @override
    async def get_or_create(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        schema: dict | None = None,
    ) -> DatasetMetadata:
        return DatasetMetadata.model_validate(
            await self._client.get_or_create(
                name=id if id is not None else name,
                schema=schema,
            )
        )

    @override
    async def list(
        self,
        *,
        unnamed: bool = False,
        limit: int | None = None,
        offset: int | None = None,
        desc: bool = False,
    ) -> DatasetListPage:
        return DatasetListPage.model_validate(
            await self._client.list(
                unnamed=unnamed,
                limit=limit,
                offset=offset,
                desc=desc,
            )
        )
