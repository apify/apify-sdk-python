from typing import Any, Dict, Optional, TypedDict, TypeVar, Union, overload

from apify_client import ApifyClientAsync
from apify_client.clients import KeyValueStoreClientAsync
from ..memory_storage.memory_storage import MemoryStorage
from ..memory_storage.resource_clients.key_value_store import KeyValueStoreClient

from ._utils import _purge_default_storages

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
    _id: str
    _name: Optional[str]
    _client: Union[KeyValueStoreClientAsync, KeyValueStoreClient]
    _persist_state_event_started: bool = False

    _cache: Dict[str, Dict]
    """Cache for persistent (auto-saved) values. When we try to set such value, the cache will be updated automatically."""

    def __init__(self, id: str, name: Optional[str], client: Union[ApifyClientAsync, MemoryStorage]) -> None:
        """TODO: docs (constructor should be "internal")."""
        self._id = id
        self._name = name
        self._client = client.key_value_store(self._id)

    @classmethod
    async def open(cls, store_id_or_name: str, client: Union[ApifyClientAsync, MemoryStorage]) -> 'KeyValueStore':
        await _purge_default_storages(client)

        id = store_id_or_name
        name = None
        key_value_store_client = client.key_value_store(store_id_or_name)
        if not await key_value_store_client.get():
            key_value_store_info = await client.key_value_stores().get_or_create(name=store_id_or_name)
            id = key_value_store_info['id']
            name = key_value_store_info['name']

        return KeyValueStore(id, name, client)

    @overload
    async def get_value(self, key: str) -> Any: # TODO: This overload stuff seems useless?
        ...
    @overload
    async def get_value(self, key: str, default_value: T) -> T:
        ...

    async def get_value(self, key: str, default_value: Optional[T] = None) -> Optional[T]:
        record = await self._client.get_record(key)
        return record['value'] if record else default_value

    # async def get_auto_saved_value(self, key: str, default_value: Optional[S] = None) -> Optional[S]:
    #     pass

    # async def for_each_key(self):
    #     pass

    # async def _ensure_persist_state_event(self):
    #     pass

    async def set_value(self, key: str, value: Optional[T], content_type: Optional[str] = None) -> None:
        pass

    async def _clear_cache(self) -> None: # TODO: Crawlee has this only for tests, so most probably not even needed
        self._cache.clear()

    async def drop(self) -> None:
        # await this.client.delete();
        # const manager = StorageManager.getManager(KeyValueStore, this.config);
        # manager.closeStorage(this);
        await self._client.delete()
