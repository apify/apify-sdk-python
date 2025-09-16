import base64

from crawlee import service_locator
from crawlee.storages import Dataset, KeyValueStore, RequestQueue
from crawlee.storages._base import Storage
from cryptography.fernet import Fernet

from apify import Configuration
from apify.storage_clients import ApifyStorageClient
_DEFAULT_EXPORT_KEY="apify-ndu-alias-map"


async def _export_alias_cache_to_kvs(
                                     kvs: KeyValueStore,
                                     encryption_key: str,
                                     excluded_instances: set[Storage] =None,
                                     kvs_key: str = _DEFAULT_EXPORT_KEY,
                                     ) -> None:
    """Export the alias cache to the kvs. Experimental method, subject to change.

    Args:
        kvs: Key value store instance to be used for export.
        encryption_key: Key used to encrypt the additional_cache_key of the cache.
        excluded_instances: These storages will not be exported.
        kvs_key: Key of the kvs to be used for the export.
    """
    cache = service_locator.storage_instance_manager._cache_by_storage_client[ApifyStorageClient]
    alias_export_map = dict[str ,str]()
    for storage_type in cache.by_alias:
        for alias in cache.by_alias[storage_type]:
            for additional_cache_key, storage in cache.by_alias[storage_type][alias]:
                if storage not in excluded_instances:
                    encrypted_key = _create_fernet(encryption_key).encrypt(additional_cache_key)
                    export_key = f'ndu-alias,{storage_type.__name__},{alias},{encrypted_key}'
                    alias_export_map[export_key] = storage.id
    if alias_export_map:
        await kvs.set_value(key=kvs_key, value=alias_export_map)

async def _load_alias_cache_from_kvs(
                                     kvs: KeyValueStore,
                                     decryption_key: str,
                                     kvs_key: str = _DEFAULT_EXPORT_KEY, )-> None:
    """Import the alias cache from the kvs. Experimental method, subject to change."""
    cache = service_locator.storage_instance_manager._cache_by_storage_client[ApifyStorageClient]
    storage_map = {'Dataset':Dataset, 'KeyValueStore':KeyValueStore, 'RequestQueue':RequestQueue}

    alias_export_map = await kvs.get_value(key=kvs_key)
    for export_key, storage_id in alias_export_map.value.items():
        # Parsing is under our control, but kind of fragile. Maybe use Pydantic model later
        _, storage_class_name, alias, encrypted_additional_cache_key = export_key.split(',')
        additional_cache_key = _create_fernet(decryption_key).decrypt(encrypted_additional_cache_key).decode()
        custom_base_url, custom_token, _ = additional_cache_key.split(";")

        custom_config = Configuration()
        custom_config.api_base_url = custom_base_url
        custom_config.token = custom_token

        # Populate the id cache by opening storage by id
        storage = await storage_map[storage_class_name].open(id=storage_id,
                                                             configuration=custom_config,
                                                             storage_client=ApifyStorageClient())
        # Populate the alias cache as well
        cache.by_alias[alias][additional_cache_key] = storage


def _create_fernet(self, token: str) -> Fernet:
    """Create Fernet for encryption based on the token."""
    # Make sure the token is of a size 32 by combination of padding and cutting
    token_length = 32
    padding= "a"
    token_32 = (token.rjust(token_length, padding))[-token_length:]
    return Fernet(base64.urlsafe_b64encode(token_32))
