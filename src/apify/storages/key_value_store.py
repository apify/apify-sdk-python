from typing import Any, AsyncIterator, Dict, Optional, Tuple, TypeVar, Union, overload

from apify_client import ApifyClientAsync
from apify_client.clients import KeyValueStoreClientAsync

# from ..consts import StorageTypes
from ..config import Configuration
from ..memory_storage import MemoryStorage
from ..memory_storage.resource_clients import KeyValueStoreClient
from ._utils import _purge_default_storages
from .storage_manager import StorageManager

T = TypeVar('T')
# S = TypeVar('S', dict)

"""
Copy-paste of method interfaces from Crawlee's implementation
constructor(options: KeyValueStoreOptions, readonly config = Configuration.getGlobalConfig()) {
    this.id = options.id;
    this.name = options.name;
    this.client = options.client.keyValueStore(this.id);
}
async getValue<T = unknown>(key: string): Promise<T | null>
async getValue<T = unknown>(key: string, defaultValue: T): Promise<T>
async getValue<T = unknown>(key: string, defaultValue?: T): Promise<T | null>
async getAutoSavedValue<T extends Dictionary = Dictionary>(key: string, defaultValue = {} as T): Promise<T>
private ensurePersistStateEvent(): void
async setValue<T>(key: string, value: T | null, options: RecordOptions = {}): Promise<void>
async drop(): Promise<void>
clearCache(): void
async forEachKey(iteratee: KeyConsumer, options: KeyValueStoreIteratorOptions = {}): Promise<void>
private async _forEachKey(iteratee: KeyConsumer, options: KeyValueStoreIteratorOptions = {}, index = 0): Promise<void>
static async open(storeIdOrName?: string | null, options: StorageManagerOptions = {}): Promise<KeyValueStore>
static async getValue<T = unknown>(key: string): Promise<T | null>
static async getValue<T = unknown>(key: string, defaultValue: T): Promise<T>
static async getValue<T = unknown>(key: string, defaultValue?: T): Promise<T | null>
static async getAutoSavedValue<T extends Dictionary = Dictionary>(key: string, defaultValue = {} as T): Promise<T>
static async setValue<T>(key: string, value: T | null, options: RecordOptions = {}): Promise<void>
static async getInput<T = Dictionary | string | Buffer>(): Promise<T | null>
"""


class KeyValueStore:
    """TODO: docs."""

    _id: str
    _name: Optional[str]
    _client: Union[KeyValueStoreClientAsync, KeyValueStoreClient]
    # _persist_state_event_started: bool = False

    # _cache: Dict[str, Dict]
    """Cache for persistent (auto-saved) values. When we try to set such value, the cache will be updated automatically."""

    def __init__(self, id: str, name: Optional[str], client: Union[ApifyClientAsync, MemoryStorage]) -> None:
        """TODO: docs (constructor should be "internal")."""
        self._id = id
        self._name = name
        self._client = client.key_value_store(self._id)

    @classmethod
    async def open(cls, store_id_or_name: Optional[str], client: Union[ApifyClientAsync, MemoryStorage], config: Configuration) -> 'KeyValueStore':
        """TODO: docs."""
        if config.purge_on_start:
            await _purge_default_storages(client)

        if not store_id_or_name:
            store_id_or_name = config.default_key_value_store_id

        key_value_store_client = client.key_value_store(store_id_or_name)
        key_value_store_info = await key_value_store_client.get()
        if not key_value_store_info:
            key_value_store_info = await client.key_value_stores().get_or_create(name=store_id_or_name)

        return KeyValueStore(key_value_store_info['id'], key_value_store_info['name'], client)

    @overload
    async def get_value(self, key: str) -> Any:  # noqa: U100
        """TODO: docs."""
        ...

    @overload
    async def get_value(self, key: str, default_value: T) -> T:  # noqa: U100
        """TODO: docs."""
        ...

    async def get_value(self, key: str, default_value: Optional[T] = None) -> Optional[T]:
        """TODO: docs."""
        record = await self._client.get_record(key)
        return record['value'] if record else default_value

    # async def get_auto_saved_value(self, key: str, default_value: Optional[S] = None) -> Optional[S]:
    #     pass

    def for_each_key(self, exclusive_start_key: Optional[str] = None) -> AsyncIterator[Tuple[Dict, int, int]]:
        """TODO: docs."""
        return self._for_each_key(exclusive_start_key)

    async def _for_each_key(self, exclusive_start_key: Optional[str] = None, index: int = 0) -> AsyncIterator[Tuple[Dict, int, int]]:
        """TODO: docs."""
        list_keys = await self._client.list_keys(exclusive_start_key=exclusive_start_key)
        for item in list_keys['items']:
            yield item, index, item['size']
            index += 1

        # TODO: Can we somehow simplify this? it seems you cannot do 'yield from' in an async method https://stackoverflow.com/a/47378063
        if list_keys['isTruncated']:
            async for x in self._for_each_key(list_keys['nextExclusiveStartKey'], index):
                yield x

    # async def _ensure_persist_state_event(self):
    #     pass

    async def set_value(self, key: str, value: Optional[T], content_type: Optional[str] = None) -> None:
        """TODO: docs."""
        if value is None:
            return await self._client.delete_record(key)

        # TODO: Why does crawlee run another stringify here?
        # value = maybeStringify(value, optionsCopy)

        return await self._client.set_record(key, value, content_type)

    # async def _clear_cache(self) -> None:  # TODO: Crawlee has this only for tests, so most probably not even needed
    #     self._cache.clear()

    async def drop(self) -> None:
        """TODO: docs."""
        await self._client.delete()
        await StorageManager.close_storage(self.__class__, self._id, self._name)
