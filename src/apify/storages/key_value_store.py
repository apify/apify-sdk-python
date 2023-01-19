from typing import Any, AsyncIterator, Dict, Optional, Tuple, TypeVar, Union, overload

from apify_client import ApifyClientAsync
from apify_client.clients import KeyValueStoreClientAsync

from .._utils import _wrap_internal
from ..config import Configuration
from ..memory_storage import MemoryStorage
from ..memory_storage.resource_clients import KeyValueStoreClient
from .storage_manager import StorageManager

T = TypeVar('T')


class KeyValueStore:
    """TODO: docs."""

    _id: str
    _name: Optional[str]
    _client: Union[KeyValueStoreClientAsync, KeyValueStoreClient]
    _config: Configuration

    def __init__(self, id: str, name: Optional[str], client: Union[ApifyClientAsync, MemoryStorage]) -> None:
        """TODO: docs (constructor should be "internal")."""
        self.get_value = _wrap_internal(self._get_value_internal, self.get_value)  # type: ignore
        self.set_value = _wrap_internal(self._set_value_internal, self.set_value)  # type: ignore
        self._id = id
        self._name = name
        self._client = client.key_value_store(self._id)
        self._config = Configuration.get_global_configuration()  # We always use the global config

    @classmethod
    async def _create_instance(cls, store_id_or_name: str, client: Union[ApifyClientAsync, MemoryStorage]) -> 'KeyValueStore':
        """TODO: docs."""
        key_value_store_client = client.key_value_store(store_id_or_name)
        key_value_store_info = await key_value_store_client.get()
        if not key_value_store_info:
            key_value_store_info = await client.key_value_stores().get_or_create(name=store_id_or_name)

        return KeyValueStore(key_value_store_info['id'], key_value_store_info.get('name'), client)

    @classmethod
    def _get_default_name(cls, config: Configuration) -> str:
        return config.default_key_value_store_id

    @overload
    @classmethod
    async def get_value(cls, key: str) -> Any:  # noqa: U100
        ...

    @overload
    @classmethod
    async def get_value(cls, key: str, default_value: T) -> T:  # noqa: U100
        ...

    @overload
    @classmethod
    async def get_value(cls, key: str, default_value: Optional[T] = None) -> Optional[T]:  # noqa: U100
        ...

    @classmethod
    async def get_value(cls, key: str, default_value: Optional[T] = None) -> Optional[T]:
        """TODO: docs."""
        store = await cls.open()
        return await store.get_value(key, default_value)

    async def _get_value_internal(self, key: str, default_value: Optional[T] = None) -> Optional[T]:
        record = await self._client.get_record(key)
        return record['value'] if record else default_value

    async def for_each_key(self, exclusive_start_key: Optional[str] = None) -> AsyncIterator[Tuple[Dict, int, int]]:
        """TODO: docs."""
        index = 0
        while True:
            list_keys = await self._client.list_keys(exclusive_start_key=exclusive_start_key)
            for item in list_keys['items']:
                yield item, index, item['size']
                index += 1

            if not list_keys['isTruncated']:
                break
            exclusive_start_key = list_keys['nextExclusiveStartKey']

    @classmethod
    async def set_value(cls, key: str, value: Optional[T], content_type: Optional[str] = None) -> None:
        """TODO: docs."""
        store = await cls.open()
        return await store.set_value(key, value, content_type)

    async def _set_value_internal(self, key: str, value: Optional[T], content_type: Optional[str] = None) -> None:
        if value is None:
            return await self._client.delete_record(key)

        # TODO: Why does crawlee run another stringify here?
        # value = maybeStringify(value, optionsCopy)

        return await self._client.set_record(key, value, content_type)

    async def drop(self) -> None:
        """TODO: docs."""
        await self._client.delete()
        await StorageManager.close_storage(self.__class__, self._id, self._name)

    @classmethod
    async def open(cls, store_id_or_name: Optional[str] = None, config: Optional[Configuration] = None) -> 'KeyValueStore':
        """TODO: docs."""
        return await StorageManager.open_storage(cls, store_id_or_name, None, config)
