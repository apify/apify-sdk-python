from __future__ import annotations

import asyncio
from logging import getLogger
from typing import TYPE_CHECKING, Any

from typing_extensions import override

from apify_client import ApifyClientAsync
from crawlee._utils.byte_size import ByteSize
from crawlee._utils.file import json_dumps
from crawlee.storage_clients._base import DatasetClient
from crawlee.storage_clients.models import DatasetItemsListPage, DatasetMetadata

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

        self._api_public_base_url = api_public_base_url
        """The public base URL for accessing the key-value store records."""

        self._lock = lock
        """A lock to ensure that only one operation is performed at a time."""

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
        configuration: Configuration,
    ) -> ApifyDatasetClient:
        """Open an Apify dataset client.

        This method creates and initializes a new instance of the Apify dataset client.
        It handles authentication, storage lookup/creation, and metadata retrieval.

        Args:
            id: The ID of an existing dataset to open. If provided, the client will connect to this specific storage.
                Cannot be used together with `name`.
            name: The name of a dataset to get or create. If a storage with this name exists, it will be opened;
                otherwise, a new one will be created. Cannot be used together with `id`.
            configuration: The configuration object containing API credentials and settings. Must include a valid
                `token` and `api_base_url`. May also contain a `default_dataset_id` for fallback when neither
                `id` nor `name` is provided.

        Returns:
            An instance for the opened or created storage client.

        Raises:
            ValueError: If the configuration is missing required fields (token, api_base_url), if both `id` and `name`
                are provided, or if neither `id` nor `name` is provided and no default storage ID is available in
                the configuration.
        """
        token = configuration.token
        if not token:
            raise ValueError(f'Apify storage client requires a valid token in Configuration (token={token}).')

        api_url = configuration.api_base_url
        if not api_url:
            raise ValueError(f'Apify storage client requires a valid API URL in Configuration (api_url={api_url}).')

        api_public_base_url = configuration.api_public_base_url
        if not api_public_base_url:
            raise ValueError(
                'Apify storage client requires a valid API public base URL in Configuration '
                f'(api_public_base_url={api_public_base_url}).'
            )

        # Create Apify client with the provided token and API URL.
        apify_client_async = ApifyClientAsync(
            token=token,
            api_url=api_url,
            max_retries=8,
            min_delay_between_retries_millis=500,
            timeout_secs=360,
        )
        apify_datasets_client = apify_client_async.datasets()

        # If both id and name are provided, raise an error.
        if id and name:
            raise ValueError('Only one of "id" or "name" can be specified, not both.')

        # If id is provided, get the storage by ID.
        if id and name is None:
            apify_dataset_client = apify_client_async.dataset(dataset_id=id)

        # If name is provided, get or create the storage by name.
        if name and id is None:
            id = DatasetMetadata.model_validate(
                await apify_datasets_client.get_or_create(name=name),
            ).id
            apify_dataset_client = apify_client_async.dataset(dataset_id=id)

        # If both id and name are None, try to get the default storage ID from environment variables.
        # The default storage ID environment variable is set by the Apify platform. It also contains
        # a new storage ID after Actor's reboot or migration.
        if id is None and name is None:
            id = configuration.default_dataset_id
            apify_dataset_client = apify_client_async.dataset(dataset_id=id)

        # Fetch its metadata.
        metadata = await apify_dataset_client.get()

        # If metadata is None, it means the storage does not exist, so we create it.
        if metadata is None:
            id = DatasetMetadata.model_validate(
                await apify_datasets_client.get_or_create(),
            ).id
            apify_dataset_client = apify_client_async.dataset(dataset_id=id)

        # Verify that the storage exists by fetching its metadata again.
        metadata = await apify_dataset_client.get()
        if metadata is None:
            raise ValueError(f'Opening dataset with id={id} and name={name} failed.')

        return cls(
            api_client=apify_dataset_client,
            api_public_base_url=api_public_base_url,
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
