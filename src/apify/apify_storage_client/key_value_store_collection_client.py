from __future__ import annotations

from typing import TYPE_CHECKING

from crawlee.base_storage_client.base_key_value_store_collection_client import BaseKeyValueStoreCollectionClient
from crawlee.models import KeyValueStoreListPage, KeyValueStoreMetadata
from typing_extensions import override

if TYPE_CHECKING:
    from apify_client.clients import KeyValueStoreCollectionClientAsync


class KeyValueStoreCollectionClient(BaseKeyValueStoreCollectionClient):
    """Key-value store collection resource client implementation based on the Apify platform storage."""

    def __init__(self, apify_dataset_collection_client: KeyValueStoreCollectionClientAsync) -> None:
        self._client = apify_dataset_collection_client

    @override
    async def get_or_create(
        self,
        *,
        id: str | None = None,  # TODO unused
        name: str | None = None,
        schema: dict | None = None,
    ) -> KeyValueStoreMetadata:
        return KeyValueStoreMetadata.model_validate(
            await self._client.get_or_create(
                name=name,
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
    ) -> KeyValueStoreListPage:
        return KeyValueStoreListPage.model_validate(await self._client.list(unnamed=unnamed, limit=limit, offset=offset, desc=desc))
