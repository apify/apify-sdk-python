from __future__ import annotations

import asyncio
from logging import getLogger
from typing import TYPE_CHECKING, Any

from typing_extensions import override
from yarl import URL

from apify_client import ApifyClientAsync
from crawlee.storage_clients._base import KeyValueStoreClient
from crawlee.storage_clients.models import KeyValueStoreMetadata, KeyValueStoreRecord, KeyValueStoreRecordMetadata

from ._models import KeyValueStoreListKeysPage
from apify._crypto import create_hmac_signature

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from apify_client.clients import KeyValueStoreClientAsync

    from apify import Configuration

logger = getLogger(__name__)


class ApifyKeyValueStoreClient(KeyValueStoreClient):
    """An Apify platform implementation of the key-value store client."""

    def __init__(
        self,
        *,
        api_client: KeyValueStoreClientAsync,
        api_public_base_url: str,
        lock: asyncio.Lock,
    ) -> None:
        """Initialize a new instance.

        Preferably use the `ApifyKeyValueStoreClient.open` class method to create a new instance.
        """
        self._api_client = api_client
        """The Apify KVS client for API operations."""

        self._api_public_base_url = api_public_base_url
        """The public base URL for accessing the key-value store records."""

        self._lock = lock
        """A lock to ensure that only one operation is performed at a time."""

    @override
    async def get_metadata(self) -> KeyValueStoreMetadata:
        metadata = await self._api_client.get()
        return KeyValueStoreMetadata.model_validate(metadata)

    @classmethod
    async def open(
        cls,
        *,
        id: str | None,
        name: str | None,
        configuration: Configuration,
    ) -> ApifyKeyValueStoreClient:
        """Open an Apify key-value store client.

        This method creates and initializes a new instance of the Apify key-value store client.
        It handles authentication, storage lookup/creation, and metadata retrieval.

        Args:
            id: The ID of an existing key-value store to open. If provided, the client will connect to this specific
                storage. Cannot be used together with `name`.
            name: The name of a key-value store to get or create. If a storage with this name exists, it will be
                opened; otherwise, a new one will be created. Cannot be used together with `id`.
            configuration: The configuration object containing API credentials and settings. Must include a valid
                `token` and `api_base_url`. May also contain a `default_key_value_store_id` for fallback when
                neither `id` nor `name` is provided.

        Returns:
            An instance for the opened or created storage client.

        Raises:
            ValueError: If the configuration is missing required fields (token, api_base_url), if both `id` and `name`
                are provided, or if neither `id` nor `name` is provided and no default storage ID is available
                in the configuration.
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

        if id and name:
            raise ValueError('Only one of "id" or "name" can be specified, not both.')

        # Create Apify client with the provided token and API URL.
        apify_client_async = ApifyClientAsync(
            token=token,
            api_url=api_url,
            max_retries=8,
            min_delay_between_retries_millis=500,
            timeout_secs=360,
        )
        apify_kvss_client = apify_client_async.key_value_stores()

        # If name is provided, get or create the storage by name.
        if name is not None and id is None:
            id = KeyValueStoreMetadata.model_validate(
                await apify_kvss_client.get_or_create(name=name),
            ).id

        # If both id and name are None, try to get the default storage ID from environment variables.
        if id is None and name is None:
            id = getattr(configuration, 'default_key_value_store_id', None)

        if id is None:
            raise ValueError(
                'Either "id" or "name" must be provided, or the storage ID must be set in environment variable.'
            )

        # Get the client for the specific storage by ID.
        apify_kvs_client = apify_client_async.key_value_store(key_value_store_id=id)

        return cls(
            api_client=apify_kvs_client,
            api_public_base_url=api_public_base_url,
            lock=asyncio.Lock(),
        )

    @override
    async def purge(self) -> None:
        raise NotImplementedError(
            'Purging key-value stores is not supported in the Apify platform. '
            'Use the `drop` method to delete the key-value store instead.'
        )

    @override
    async def drop(self) -> None:
        async with self._lock:
            await self._api_client.delete()

    @override
    async def get_value(self, key: str) -> KeyValueStoreRecord | None:
        response = await self._api_client.get_record(key)
        record = KeyValueStoreRecord.model_validate(response) if response else None
        await self._update_metadata()
        return record

    @override
    async def set_value(self, key: str, value: Any, content_type: str | None = None) -> None:
        async with self._lock:
            await self._api_client.set_record(
                key=key,
                value=value,
                content_type=content_type,
            )
            await self._update_metadata()

    @override
    async def delete_value(self, key: str) -> None:
        async with self._lock:
            await self._api_client.delete_record(key=key)
            await self._update_metadata()

    @override
    async def iterate_keys(
        self,
        *,
        exclusive_start_key: str | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[KeyValueStoreRecordMetadata]:
        count = 0

        while True:
            response = await self._api_client.list_keys(exclusive_start_key=exclusive_start_key)
            list_key_page = KeyValueStoreListKeysPage.model_validate(response)

            for item in list_key_page.items:
                # Convert KeyValueStoreKeyInfo to KeyValueStoreRecordMetadata
                record_metadata = KeyValueStoreRecordMetadata(
                    key=item.key,
                    size=item.size,
                    content_type='application/octet-stream',  # Content type not available from list_keys
                )
                yield record_metadata
                count += 1

                # If we've reached the limit, stop yielding
                if limit and count >= limit:
                    break

            # If we've reached the limit or there are no more pages, exit the loop
            if (limit and count >= limit) or not list_key_page.is_truncated:
                break

            exclusive_start_key = list_key_page.next_exclusive_start_key

        await self._update_metadata()

    @override
    async def record_exists(self, key: str) -> bool:
        return await self._api_client.record_exists(key=key)

    async def get_public_url(self, key: str) -> str:
        """Get a URL for the given key that may be used to publicly access the value in the remote key-value store.

        Args:
            key: The key for which the URL should be generated.

        Returns:
            A public URL that can be used to access the value of the given key in the KVS.
        """
        if self._api_client.resource_id is None:
            raise ValueError('resource_id cannot be None when generating a public URL')

        public_url = (
            URL(self._api_public_base_url) / 'v2' / 'key-value-stores' / self._api_client.resource_id / 'records' / key
        )
        metadata = await self.get_metadata()

        if metadata.model_extra is not None:
            url_signing_secret_key = metadata.model_extra.get('urlSigningSecretKey')
            if url_signing_secret_key is not None:
                public_url = public_url.with_query(signature=create_hmac_signature(url_signing_secret_key, key))

        return str(public_url)

    async def _update_metadata(self) -> None:
        """Update the key-value store metadata with current information."""
        metadata = await self._api_client.get()
        self._metadata = KeyValueStoreMetadata.model_validate(metadata)
