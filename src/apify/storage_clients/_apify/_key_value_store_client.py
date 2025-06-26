from __future__ import annotations

import asyncio
import os
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
    from datetime import datetime

    from apify_client.clients import KeyValueStoreClientAsync
    from crawlee.configuration import Configuration

logger = getLogger(__name__)


class ApifyKeyValueStoreClient(KeyValueStoreClient):
    """An Apify platform implementation of the key-value store client."""

    def __init__(
        self,
        *,
        id: str,
        name: str | None,
        created_at: datetime,
        accessed_at: datetime,
        modified_at: datetime,
        api_client: KeyValueStoreClientAsync,
    ) -> None:
        """Initialize a new instance.

        Preferably use the `ApifyKeyValueStoreClient.open` class method to create a new instance.
        """
        self._metadata = KeyValueStoreMetadata(
            id=id,
            name=name,
            created_at=created_at,
            accessed_at=accessed_at,
            modified_at=modified_at,
        )

        self._api_client = api_client
        """The Apify key-value store client for API operations."""

        self._lock = asyncio.Lock()
        """A lock to ensure that only one operation is performed at a time."""

    @property
    @override
    def metadata(self) -> KeyValueStoreMetadata:
        return self._metadata

    @override
    @classmethod
    async def open(
        cls,
        *,
        id: str | None,
        name: str | None,
        configuration: Configuration,
    ) -> ApifyKeyValueStoreClient:
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

        apify_kvss_client = apify_client_async.key_value_stores()

        if id and name:
            raise ValueError('Only one of "id" or "name" can be specified, not both.')

        # If name is provided, get or create the storage by name.
        if name is not None and id is None:
            id = KeyValueStoreMetadata.model_validate(
                await apify_kvss_client.get_or_create(name=name),
            ).id

        # If both id and name are None, try to get the default storage ID from environment variables.
        if id is None and name is None:
            id = os.environ.get(
                'ACTOR_DEFAULT_KEY_VALUE_STORE_ID',
                None,
            ) or os.environ.get(
                'APIFY_DEFAULT_KEY_VALUE_STORE_ID',
                None,
            )

        if id is None:
            raise ValueError(
                'Either "id" or "name" must be provided, or the storage ID must be set in environment variable.'
            )

        # Get the client for the specific storage by ID.
        apify_kvs_client = apify_client_async.key_value_store(key_value_store_id=id)

        # Fetch its metadata.
        metadata = KeyValueStoreMetadata.model_validate(await apify_kvs_client.get())

        return cls(
            id=metadata.id,
            name=metadata.name,
            created_at=metadata.created_at,
            accessed_at=metadata.accessed_at,
            modified_at=metadata.modified_at,
            api_client=apify_kvs_client,
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

    async def get_public_url(self, key: str) -> str:
        """Get a URL for the given key that may be used to publicly access the value in the remote key-value store.

        Args:
            key: The key for which the URL should be generated.
        """
        if self._api_client.resource_id is None:
            raise ValueError('resource_id cannot be None when generating a public URL')

        public_url = (
            URL(self._api_client.base_url) / 'v2' / 'key-value-stores' / self._api_client.resource_id / 'records' / key
        )

        key_value_store = self.metadata

        if key_value_store and key_value_store.model_extra:
            url_signing_secret_key = key_value_store.model_extra.get('urlSigningSecretKey')
            if url_signing_secret_key:
                public_url = public_url.with_query(signature=create_hmac_signature(url_signing_secret_key, key))

        return str(public_url)

    async def _update_metadata(self) -> None:
        """Update the key-value store metadata with current information."""
        metadata = await self._api_client.get()
        self._metadata = KeyValueStoreMetadata.model_validate(metadata)
