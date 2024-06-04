from __future__ import annotations

from typing import TYPE_CHECKING, Any

from crawlee.base_storage_client.base_key_value_store_client import BaseKeyValueStoreClient
from crawlee.models import KeyValueStoreListKeysPage, KeyValueStoreMetadata, KeyValueStoreRecord
from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from apify_client.clients import KeyValueStoreClientAsync


class KeyValueStoreClient(BaseKeyValueStoreClient):
    """Key-value store resource client implementation based on the Apify platform storage."""

    def __init__(self, apify_key_value_store_client: KeyValueStoreClientAsync) -> None:
        self._client = apify_key_value_store_client

    @override
    async def get(self) -> KeyValueStoreMetadata | None:
        result = await self._client.get()
        return KeyValueStoreMetadata.model_validate(result) if result else None

    @override
    async def update(
        self,
        *,
        name: str | None = None,
    ) -> KeyValueStoreMetadata:
        return KeyValueStoreMetadata.model_validate(await self._client.update())

    @override
    async def delete(self) -> None:
        await self._client.delete()

    @override
    async def list_keys(
        self,
        *,
        limit: int = 1000,
        exclusive_start_key: str | None = None,
    ) -> KeyValueStoreListKeysPage:
        return KeyValueStoreListKeysPage.model_validate(await self._client.list_keys())

    @override
    async def get_record(self, key: str) -> KeyValueStoreRecord | None:
        result = await self._client.get_record(key)
        return KeyValueStoreRecord.model_validate(result) if result else None

    @override
    async def get_record_as_bytes(self, key: str) -> KeyValueStoreRecord | None:
        result = await self._client.get_record_as_bytes(key)
        return KeyValueStoreRecord.model_validate(result) if result else None

    @override
    async def stream_record(self, key: str) -> AsyncIterator[KeyValueStoreRecord | None]:  # TODO incorrect type
        async with self._client.stream_record(key) as response:
            return KeyValueStoreRecord.model_validate(response)

    @override
    async def set_record(self, key: str, value: Any, content_type: str | None = None) -> None:
        await self._client.set_record(
            key=key,
            value=value,
            content_type=content_type,
        )

    @override
    async def delete_record(self, key: str) -> None:
        await self._client.delete_record(
            key=key,
        )
