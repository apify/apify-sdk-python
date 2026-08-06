from __future__ import annotations

import asyncio
import json
from logging import getLogger
from typing import TYPE_CHECKING

from typing_extensions import override

from crawlee._utils.byte_size import ByteSize
from crawlee.storage_clients._base import DatasetClient
from crawlee.storage_clients.models import DatasetItemsListPage, DatasetMetadata

from ._api_client_creation import create_storage_api_client
from apify._charging import charge_lock_if_charging
from apify.storage_clients._ppe_dataset_mixin import DatasetClientPpeMixin

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping, Sequence

    from apify_client._resource_clients import DatasetClientAsync
    from crawlee._types import JsonSerializable

    from apify import Configuration

logger = getLogger(__name__)


class ApifyDatasetClient(DatasetClient, DatasetClientPpeMixin):
    """An Apify platform implementation of the dataset client."""

    _MAX_PAYLOAD_SIZE = ByteSize.from_mb(9)
    """Maximum size for a single payload."""

    _SAFETY_BUFFER_COEFFICIENT = 0.01 / 100  # 0.01%
    """Percentage buffer to reduce payload limit slightly for safety."""

    _EFFECTIVE_LIMIT_SIZE = _MAX_PAYLOAD_SIZE - (_MAX_PAYLOAD_SIZE * _SAFETY_BUFFER_COEFFICIENT)
    """Calculated payload limit considering safety buffer."""

    def __init__(
        self,
        *,
        api_client: DatasetClientAsync,
        lock: asyncio.Lock | None = None,  # noqa: ARG002 - no-op, kept for backward compatibility
    ) -> None:
        """Initialize a new instance.

        Preferably use the `ApifyDatasetClient.open` class method to create a new instance.
        """
        DatasetClient.__init__(self)
        DatasetClientPpeMixin.__init__(self)

        self._api_client = api_client
        """The Apify dataset client for API operations."""

    @override
    async def get_metadata(self) -> DatasetMetadata:
        metadata = await self._api_client.get()

        if metadata is None:
            raise ValueError('Failed to retrieve dataset metadata.')

        return DatasetMetadata(
            id=metadata.id,
            name=metadata.name,
            created_at=metadata.created_at,
            modified_at=metadata.modified_at,
            accessed_at=metadata.accessed_at,
            item_count=metadata.item_count,
        )

    @classmethod
    async def open(
        cls,
        *,
        id: str | None,
        name: str | None,
        alias: str | None,
        configuration: Configuration,
    ) -> ApifyDatasetClient:
        """Open an Apify dataset client.

        This method creates and initializes a new instance of the Apify dataset client.
        It handles authentication, storage lookup/creation, and metadata retrieval.

        Args:
            id: The ID of the dataset to open. If provided, searches for existing dataset by ID.
                Mutually exclusive with name and alias.
            name: The name of the dataset to open (global scope, persists across runs).
                Mutually exclusive with id and alias.
            alias: The alias of the dataset to open (run scope, creates unnamed storage).
                Mutually exclusive with id and name.
            configuration: The configuration object containing API credentials and settings. Must include a valid
                `token` and `api_base_url`. May also contain a `default_dataset_id` for fallback when neither
                `id`, `name`, nor `alias` is provided.

        Returns:
            An instance for the opened or created storage client.

        Raises:
            ValueError: If the configuration is missing required fields (token, api_base_url), if more than one of
                `id`, `name`, or `alias` is provided, or if none are provided and no default storage ID is available
                in the configuration.
        """
        api_client = await create_storage_api_client(
            storage_type='Dataset',
            configuration=configuration,
            alias=alias,
            name=name,
            id=id,
        )

        dataset_client = cls(api_client=api_client)

        dataset_client.is_default_dataset = (
            alias is None and name is None and (id is None or id == configuration.default_dataset_id)
        )

        return dataset_client

    @override
    async def purge(self) -> None:
        raise NotImplementedError(
            'Purging datasets is not supported in the Apify platform. '
            'Use the `drop` method to delete the dataset instead.'
        )

    @override
    async def drop(self) -> None:
        await self._api_client.delete()

    @override
    async def push_data(self, data: Sequence[Mapping[str, JsonSerializable]] | Mapping[str, JsonSerializable]) -> None:
        # Pushing mutates no client state - `push_items` is a stateless API call - so concurrent pushes only need
        # the charge lock, which keeps the limit reservation and the charge atomic for pay-per-event runs.
        async with charge_lock_if_charging():
            items = data if self._is_sequence_of_items(data) else [data]
            if not items:
                return
            limit = self._compute_limit_for_push(len(items))
            items = items[:limit]

            offset = 0
            while offset < len(items):
                chunk, offset = await asyncio.to_thread(self._serialize_chunk, items, offset)
                await self._api_client.push_items(items=chunk)

            await self._charge_for_items(count_items=limit)

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
        unwind: list[str] | None = None,
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
        return DatasetItemsListPage.model_validate(vars(response))

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
        unwind: list[str] | None = None,
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

    @classmethod
    def _serialize_chunk(cls, items: Sequence[Mapping[str, JsonSerializable]], offset: int) -> tuple[str, int]:
        """Serialize items starting at `offset` into one JSON array staying within the payload size limit.

        The array holds as many consecutive items as fit within `_EFFECTIVE_LIMIT_SIZE`, always at least one. Output
        is compact JSON - it goes straight on the wire. This is CPU-bound and blocking; call it via `asyncio.to_thread`.

        Args:
            items: The items to serialize.
            offset: Index of the first item to serialize.

        Returns:
            The JSON array string and the index of the first item that did not fit into it.

        Raises:
            ValueError: If an item is not JSON serializable or on its own exceeds the size limit.
        """
        limit = cls._EFFECTIVE_LIMIT_SIZE.bytes
        payloads: list[str] = []
        chunk_size = 2  # Add 2 bytes for [] wrapper.

        for index in range(offset, len(items)):
            try:
                payload = json.dumps(items[index], ensure_ascii=False, separators=(',', ':'), default=str)
            except Exception as exc:
                raise ValueError(f'Data item at index {index} is not serializable to JSON.') from exc

            payload_size = len(payload.encode('utf-8'))
            if payload_size > limit:
                raise ValueError(
                    f'Data item at index {index} is too large '
                    f'(size: {ByteSize(payload_size)}, limit: {cls._EFFECTIVE_LIMIT_SIZE})'
                )

            if payloads and chunk_size + payload_size > limit:
                return f'[{",".join(payloads)}]', index

            payloads.append(payload)
            chunk_size += payload_size + 1  # Add 1 byte for ',' separator.

        return f'[{",".join(payloads)}]', len(items)
