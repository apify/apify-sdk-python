from __future__ import annotations

import base64
import logging
from logging import getLogger
from typing import TYPE_CHECKING

from cryptography.fernet import Fernet

from apify_client import ApifyClientAsync
from crawlee.storages import Dataset, KeyValueStore, RequestQueue

from apify._configuration import Configuration

if TYPE_CHECKING:
    from apify_client.clients import KeyValueStoreClientAsync


logger = getLogger(__name__)

_ALIAS_MAPPING_KEY = '__STORAGE_ALIASES_MAPPING'
_StorageT = type[Dataset | KeyValueStore | RequestQueue]


class _Alias:
    """Class representing an alias for a storage.

    It includes helper methods for serialization/deserialization and storing to default kvs.
    """

    ALIAS_SEPARATOR = ','
    ADDITIONAL_CACHE_KEY_SEPARATOR = ';'

    def __init__(self, storage_type: _StorageT, alias: str, token: str, api_url: str) -> None:
        self.storage_type = storage_type
        self.alias = alias
        self.api_url = api_url
        # Token used to access the storage
        self.token = token

    @classmethod
    def get_additional_cache_key(cls, api_url: str, token: str, *, encrypted: bool = False) -> str:
        """Return additional cache key.

        Args:
            api_url: Api url used to open the storage.
            token: Token used to open the storage.
            encrypted: Whether the token should be encrypted in the cache key.

        Returns:
            Serialized additional cache key string.

        """
        if not encrypted:
            return cls.ADDITIONAL_CACHE_KEY_SEPARATOR.join([api_url, token])

        encryption_key = Configuration.get_global_configuration().token
        if encryption_key is not None:
            encrypted_token = cls._create_fernet(encryption_key).encrypt(token.encode()).decode()
            return cls.ADDITIONAL_CACHE_KEY_SEPARATOR.join([api_url, encrypted_token])
        raise ValueError('Configuration.token not set.')

    @property
    def additional_cache_key(self) -> str:
        """Serialized unencrypted additional cache key string."""
        return self.get_additional_cache_key(self.api_url, self.token, encrypted=False)

    @classmethod
    def from_exported_string(cls, alias_as_string: str) -> _Alias:
        """Create _Alias from previously serialized _Alias."""
        storage_map: dict[str, _StorageT] = {
            'Dataset': Dataset,
            'KeyValueStore': KeyValueStore,
            'RequestQueue': RequestQueue,
        }
        _, storage_class_name, alias, encrypted_additional_cache_key = alias_as_string.split(cls.ALIAS_SEPARATOR)
        api_url, encrypted_token = encrypted_additional_cache_key.split(cls.ADDITIONAL_CACHE_KEY_SEPARATOR)

        decryption_key = Configuration.get_global_configuration().token
        if decryption_key is not None:
            token = cls._create_fernet(decryption_key).decrypt(encrypted_token).decode()
        else:
            raise ValueError('Configuration.token not set.')

        return cls(storage_type=storage_map[storage_class_name], alias=alias, api_url=api_url, token=token)

    def get_storage_key(self) -> str:
        return self.ALIAS_SEPARATOR.join(
            [
                self.storage_type.__name__,
                self.alias,
                self.get_additional_cache_key(api_url=self.api_url, token=self.token, encrypted=True),
            ]
        )

    @staticmethod
    def _create_fernet(token: str) -> Fernet:
        """Create Fernet for encryption based on the token."""
        # Make sure the token is of a size 32 by combination of padding and cutting
        token_length = 32
        padding = 'a'
        token_32 = ((token.rjust(token_length, padding))[-token_length:]).encode()
        return Fernet(base64.urlsafe_b64encode(token_32))

    async def store_mapping_to_apify_kvs(self, storage_id: str) -> None:
        """Add _Alias and related storage id to the mapping in default kvs."""
        if not Configuration.get_global_configuration().is_at_home:
            logging.getLogger(__name__).warning(
                'Alias storage limited retention is only supported on Apify platform. Storage is not exported.'
            )
            return

        default_kvs_client = await self.get_default_kvs_client()
        await default_kvs_client.get()

        try:
            record = await default_kvs_client.get_record(_ALIAS_MAPPING_KEY)

            # get_record can return {key: ..., value: ..., content_type: ...}
            if isinstance(record, dict) and 'value' in record:
                record = record['value']

            # Update or create the record with the new alias mapping

            if isinstance(record, dict):
                record[self.get_storage_key()] = storage_id
            else:
                record = {self.get_storage_key(): storage_id}

            # Store the mapping back in the KVS.
            await default_kvs_client.set_record(_ALIAS_MAPPING_KEY, record)
        except Exception as exc:
            logger.warning(f'Error accessing alias mapping for {self.alias}: {exc}')

    @staticmethod
    async def get_default_kvs_client() -> KeyValueStoreClientAsync:
        """Get a client for the default key-value store."""
        # Create Apify client with the provided token and API URL

        configuration = Configuration.get_global_configuration()
        if not configuration.is_at_home:
            raise NotImplementedError('Alias storages are only supported on Apify platform at the moment.')

        apify_client_async = ApifyClientAsync(
            token=configuration.token,
            api_url=configuration.api_base_url,
            max_retries=8,
            min_delay_between_retries_millis=500,
            timeout_secs=360,
        )

        return apify_client_async.key_value_store(key_value_store_id=configuration.default_key_value_store_id)
