from __future__ import annotations

import asyncio
import warnings
from logging import getLogger
from typing import TYPE_CHECKING, Any

from typing_extensions import override

from crawlee._utils.byte_size import ByteSize
from crawlee._utils.file import json_dumps
from crawlee.storage_clients._base import DatasetClient
from crawlee.storage_clients.models import DatasetItemsListPage, DatasetMetadata

from ._api_client_creation import create_storage_api_client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from apify_client.clients import DatasetClientAsync
    from crawlee._types import JsonSerializable

    from apify import Configuration

logger = getLogger(__name__)


class ApifyDatasetClient(DatasetClient):
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
        api_public_base_url: str,
        lock: asyncio.Lock,
    ) -> None:
        """Initialize a new instance.

        Preferably use the `ApifyDatasetClient.open` class method to create a new instance.
        """
        self._api_client = api_client
        """The Apify dataset client for API operations."""

        self._lock = lock
        """A lock to ensure that only one operation is performed at a time."""

        if api_public_base_url:
            # Remove in version 4.0, https://github.com/apify/apify-sdk-python/issues/635
            warnings.warn(
                'api_public_base_url argument is deprecated and will be removed in version 4.0.0',
                DeprecationWarning,
                stacklevel=2,
            )

    @override
    async def get_metadata(self) -> DatasetMetadata:
        metadata = await self._api_client.get()
        return DatasetMetadata.model_validate(metadata)

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

        return cls(
            api_client=api_client,
            api_public_base_url='',  # Remove in version 4.0, https://github.com/apify/apify-sdk-python/issues/635
            lock=asyncio.Lock(),
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
        async def payloads_generator() -> AsyncIterator[str]:
            for index, item in enumerate(data):
                yield await self._check_and_serialize(item, index)

        async with self._lock:
            # Handle lists
            if isinstance(data, list):
                # Invoke client in series to preserve the order of data
                async for items in self._chunk_by_size(payloads_generator()):
                    await self._api_client.push_items(items=items)

            # Handle singular items
            else:
                items = await self._check_and_serialize(data)
                await self._api_client.push_items(items=items)

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
    async def _check_and_serialize(cls, item: JsonSerializable, index: int | None = None) -> str:
        """Serialize a given item to JSON, checks its serializability and size against a limit.

        Args:
            item: The item to serialize.
            index: Index of the item, used for error context.

        Returns:
            Serialized JSON string.

        Raises:
            ValueError: If item is not JSON serializable or exceeds size limit.
        """
        s = ' ' if index is None else f' at index {index} '

        try:
            payload = await json_dumps(item)
        except Exception as exc:
            raise ValueError(f'Data item{s}is not serializable to JSON.') from exc

        payload_size = ByteSize(len(payload.encode('utf-8')))
        if payload_size > cls._EFFECTIVE_LIMIT_SIZE:
            raise ValueError(f'Data item{s}is too large (size: {payload_size}, limit: {cls._EFFECTIVE_LIMIT_SIZE})')

        return payload

    async def _chunk_by_size(self, items: AsyncIterator[str]) -> AsyncIterator[str]:
        """Yield chunks of JSON arrays composed of input strings, respecting a size limit.

        Groups an iterable of JSON string payloads into larger JSON arrays, ensuring the total size
        of each array does not exceed `EFFECTIVE_LIMIT_SIZE`. Each output is a JSON array string that
        contains as many payloads as possible without breaching the size threshold, maintaining the
        order of the original payloads. Assumes individual items are below the size limit.

        Args:
            items: Iterable of JSON string payloads.

        Yields:
            Strings representing JSON arrays of payloads, each staying within the size limit.
        """
        last_chunk_size = ByteSize(2)  # Add 2 bytes for [] wrapper.
        current_chunk = []

        async for payload in items:
            payload_size = ByteSize(len(payload.encode('utf-8')))

            if last_chunk_size + payload_size <= self._EFFECTIVE_LIMIT_SIZE:
                current_chunk.append(payload)
                last_chunk_size += payload_size + ByteSize(1)  # Add 1 byte for ',' separator.
            else:
                yield f'[{",".join(current_chunk)}]'
                current_chunk = [payload]
                last_chunk_size = payload_size + ByteSize(2)  # Add 2 bytes for [] wrapper.

        yield f'[{",".join(current_chunk)}]'
