from typing import Any, AsyncIterator, NamedTuple, Optional, TypedDict, TypeVar, Union, overload

from apify_client import ApifyClientAsync
from apify_client.clients import KeyValueStoreClientAsync

from .._utils import _wrap_internal
from ..config import Configuration
from ..memory_storage import MemoryStorage
from ..memory_storage.resource_clients import KeyValueStoreClient
from .storage_manager import StorageManager

T = TypeVar('T')
IterateKeysInfo = TypedDict('IterateKeysInfo', {'size': int})
IterateKeysTuple = NamedTuple('IterateKeysTuple', [('key', str), ('info', IterateKeysInfo)])


class KeyValueStore:
    """The `KeyValueStore` class represents a key-value store.

    You can imagine it as a simple data storage that is used
    for saving and reading data records or files. Each data record is
    represented by a unique key and associated with a MIME content type.

    Do not instantiate this class directly, use the `Actor.open_key_value_store()` function instead.

    Each crawler run is associated with a default key-value store, which is created exclusively
    for the run. By convention, the crawler input and output are stored into the
    default key-value store under the `INPUT` and `OUTPUT` key, respectively.
    Typically, input and output are JSON files, although it can be any other format.
    To access the default key-value store directly, you can use the
    `KeyValueStore.get_value` and `KeyValueStore.set_value` convenience functions.

    `KeyValueStore` stores its data either on local disk or in the Apify cloud,
    depending on whether the `APIFY_LOCAL_STORAGE_DIR` or `APIFY_TOKEN` environment variables are set.

    If the `APIFY_LOCAL_STORAGE_DIR` environment variable is set, the data is stored in
    the local directory in the following files:
    ```
    {APIFY_LOCAL_STORAGE_DIR}/key_value_stores/{STORE_ID}/{INDEX}.{EXT}
    ```
    Note that `{STORE_ID}` is the name or ID of the key-value store. The default key-value store has ID: `default`,
    unless you override it by setting the `APIFY_DEFAULT_KEY_VALUE_STORE_ID` environment variable.
    The `{KEY}` is the key of the record and `{EXT}` corresponds to the MIME content type of the data value.

    If the `APIFY_TOKEN` environment variable is set but `APIFY_LOCAL_STORAGE_DIR` is not, the data is stored in the
    [Apify Key-value store](https://docs.apify.com/storage/key-value-store) cloud storage.
    """

    _id: str
    _name: Optional[str]
    _client: Union[KeyValueStoreClientAsync, KeyValueStoreClient]

    def __init__(self, id: str, name: Optional[str], client: Union[ApifyClientAsync, MemoryStorage]) -> None:
        """Create a `KeyValueStore` instance.

        Do not use the constructor directly, use the `KeyValueStore.open` function instead.

        Args:
            id (str): ID of the key-value store.
            name (str, optional): Name of the key-value store.
            client (ApifyClientAsync or MemoryStorage): The storage client which should be used.
        """
        self.get_value = _wrap_internal(self._get_value_internal, self.get_value)  # type: ignore
        self.set_value = _wrap_internal(self._set_value_internal, self.set_value)  # type: ignore
        self._id = id
        self._name = name
        self._client = client.key_value_store(self._id)

    @classmethod
    async def _create_instance(cls, store_id_or_name: str, client: Union[ApifyClientAsync, MemoryStorage]) -> 'KeyValueStore':
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
    async def get_value(cls, key: str) -> Any:
        ...

    @overload
    @classmethod
    async def get_value(cls, key: str, default_value: T) -> T:
        ...

    @overload
    @classmethod
    async def get_value(cls, key: str, default_value: Optional[T] = None) -> Optional[T]:
        ...

    @classmethod
    async def get_value(cls, key: str, default_value: Optional[T] = None) -> Optional[T]:
        """Get a value from the key-value store.

        Args:
            key (str): Key of the record to retrieve.
            default_value (Any, optional): Default value returned in case the record does not exist.

        Returns:
            Any: The value associated with the given key. `default_value` is used in case the record does not exist.
        """
        store = await cls.open()
        return await store.get_value(key, default_value)

    async def _get_value_internal(self, key: str, default_value: Optional[T] = None) -> Optional[T]:
        record = await self._client.get_record(key)
        return record['value'] if record else default_value

    async def iterate_keys(self, exclusive_start_key: Optional[str] = None) -> AsyncIterator[IterateKeysTuple]:
        """Iterate over the keys in the key-value store.

        Args:
            exclusive_start_key (str, optional): All keys up to this one (including) are skipped from the result.

        Yields:
            IterateKeysTuple: A tuple `(key, info)`,
                where `key` is the record key, and `info` is an object that contains a single property `size`
                indicating size of the record in bytes.
        """
        while True:
            list_keys = await self._client.list_keys(exclusive_start_key=exclusive_start_key)
            for item in list_keys['items']:
                yield IterateKeysTuple(item['key'], {'size': item['size']})

            if not list_keys['isTruncated']:
                break
            exclusive_start_key = list_keys['nextExclusiveStartKey']

    @classmethod
    async def set_value(cls, key: str, value: Optional[T], content_type: Optional[str] = None) -> None:
        """Set or delete a value in the key-value store.

        Args:
            key (str): The key under which the value should be saved.
            value (Any, optional): The value to save. If the value is `None`, the corresponding key-value pair will be deleted.
            content_type (str, optional): The content type of the saved value.
        """
        store = await cls.open()
        return await store.set_value(key, value, content_type)

    async def _set_value_internal(self, key: str, value: Optional[T], content_type: Optional[str] = None) -> None:
        if value is None:
            return await self._client.delete_record(key)

        # TODO: Why does crawlee run another stringify here?
        # value = maybeStringify(value, optionsCopy)

        return await self._client.set_record(key, value, content_type)

    async def drop(self) -> None:
        """Remove the key-value store either from the Apify cloud storage or from the local directory."""
        await self._client.delete()
        await StorageManager.close_storage(self.__class__, self._id, self._name)

    @classmethod
    async def open(cls, store_id_or_name: Optional[str] = None, config: Optional[Configuration] = None) -> 'KeyValueStore':
        """Open a key-value store.

        Key-value stores are used to store records or files, along with their MIME content type.
        The records are stored and retrieved using a unique key.
        The actual data is stored either on a local filesystem or in the Apify cloud.

        Args:
            key_value_store_id_or_name (str, optional): ID or name of the key-value store to be opened.
                If not provided, the method returns the default key-value store associated with the actor run.
            config (Configuration, optional): A `Configuration` instance, uses global configuration if omitted.

        Returns:
            KeyValueStore: An instance of the `KeyValueStore` class for the given ID or name.
        """
        return await StorageManager.open_storage(cls, store_id_or_name, None, config)
