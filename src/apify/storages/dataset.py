import math
from typing import Any, AsyncIterator, Dict, List, Optional, TypedDict, TypeVar, Union, overload

from apify_client import ApifyClientAsync
from apify_client._utils import ListPage
from apify_client.clients import DatasetClientAsync

from .._types import JSONSerializable
from ..config import Configuration
from ..memory_storage import MemoryStorage
from ..memory_storage.resource_clients import DatasetClient
from ._utils import _purge_default_storages
from .key_value_store import KeyValueStore

"""
Copy-paste of method interfaces from Crawlee's implementation
constructor(options: DatasetOptions, readonly config = Configuration.getGlobalConfig()) {
    this.id = options.id;
    this.name = options.name;
    this.client = options.client.dataset(this.id) as DatasetClient<Data>;
}
async pushData(data: Data | Data[]): Promise<void>
async getData(options: DatasetDataOptions = {}): Promise<DatasetContent<Data>>
async exportTo(key: string, options?: ExportOptions, contentType?: string): Promise<void>
async exportToJSON(key: string, options?: Omit<ExportOptions, 'fromDataset'>)
async exportToCSV(key: string, options?: Omit<ExportOptions, 'fromDataset'>)
static async exportToJSON(key: string, options?: ExportOptions)
static async exportToCSV(key: string, options?: ExportOptions)
async getInfo(): Promise<DatasetInfo | undefined>
async forEach(iteratee: DatasetConsumer<Data>, options: DatasetIteratorOptions = {}, index = 0): Promise<void>
async map<R>(iteratee: DatasetMapper<Data, R>, options: DatasetIteratorOptions = {}): Promise<R[]>
async reduce<T>(iteratee: DatasetReducer<T, Data>, memo: T, options: DatasetIteratorOptions = {}): Promise<T>
async drop(): Promise<void>
static async open<Data extends Dictionary = Dictionary>(datasetIdOrName?: string | null, options: StorageManagerOptions = {}): Promise<Dataset<Data>>
static async pushData<Data extends Dictionary = Dictionary>(item: Data | Data[]): Promise<void>
static async getData<Data extends Dictionary = Dictionary>(options: DatasetDataOptions = {}): Promise<DatasetContent<Data>>
"""


class Dataset:
    _id: str
    _name: Optional[str]
    _client: Union[DatasetClientAsync, DatasetClient]

    def __init__(self, id: str, name: Optional[str], client: Union[ApifyClientAsync, MemoryStorage]) -> None:
        """TODO: docs (constructor should be "internal")."""
        self._id = id
        self._name = name
        self._client = client.dataset(self._id)

    @classmethod
    async def open(cls, dataset_id_or_name: Optional[str], client: Union[ApifyClientAsync, MemoryStorage], config: Configuration) -> 'Dataset':
        if config.purge_on_start:
            await _purge_default_storages(client)

        if not dataset_id_or_name:
            dataset_id_or_name = config.default_dataset_id

        dataset_client = client.dataset(dataset_id_or_name)
        dataset_info = await dataset_client.get()
        if not dataset_info:
            dataset_info = await client.datasets().get_or_create(name=dataset_id_or_name)

        return Dataset(dataset_info['id'], dataset_info['name'], client)

    async def push_data(self, data: JSONSerializable) -> None:
        # const dispatch = (payload: string) => this.client.pushItems(payload);
        # const limit = MAX_PAYLOAD_SIZE_BYTES - Math.ceil(MAX_PAYLOAD_SIZE_BYTES * SAFETY_BUFFER_PERCENT);

        # // Handle singular Objects
        # if (!Array.isArray(data)) {
        #     const payload = checkAndSerialize(data, limit);
        #     return dispatch(payload);
        # }

        # // Handle Arrays
        # const payloads = data.map((item, index) => checkAndSerialize(item, limit, index));
        # const chunks = chunkBySize(payloads, limit);

        # // Invoke client in series to preserve order of data
        # for (const chunk of chunks) {
        #     await dispatch(chunk);
        # }
        # TODO: Implement the size chunking mechanism from crawlee
        # limit = MAX_PAYLOAD_SIZE_BYTES - math.ceil(MAX_PAYLOAD_SIZE_BYTES * SAFETY_BUFFER_PERCENT)
        await self._client.push_items(data)

    async def get_data(
        self,
        *,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
        clean: Optional[bool] = None,
        desc: Optional[bool] = None,
        fields: Optional[List[str]] = None,
        omit: Optional[List[str]] = None,
        unwind: Optional[str] = None,
        skip_empty: Optional[bool] = None,
        skip_hidden: Optional[bool] = None,
        flatten: Optional[List[str]] = None,
        view: Optional[str] = None,
    ) -> ListPage:
        # try {
        #     return await this.client.listItems(options);
        # } catch (e) {
        #     const error = e as Error;
        #     if (error.message.includes('Cannot create a string longer than')) {
        #         throw new Error('dataset.getData(): The response is too large for parsing. You can fix this by lowering the "limit" option.');
        #     }
        #     throw e;
        # }
        return await self._client.list_items(
            offset=offset,
            limit=limit,
            desc=desc,
            clean=clean,
            fields=fields,
            omit=omit,
            unwind=unwind,
            skip_empty=skip_empty,
            skip_hidden=skip_hidden,
            flatten=flatten,
            view=view,
        )

    async def export_to(self, key: str, from_dataset: str, to_key_value_store: Optional[str] = None, content_type: Optional[str] = None) -> None:
        raise NotImplementedError('Not implemented yet')
        # key_value_store = await KeyValueStore.open(to_key_value_store, self._client, Configuration.get_global_configuration())
        # const kvStore = await KeyValueStore.open(options?.toKVS ?? null);
        # const items: Data[] = [];

        # const fetchNextChunk = async (offset = 0): Promise<void> => {
        #     const limit = 1000;
        #     const value = await this.client.listItems({ offset, limit });

        #     if (value.count === 0) {
        #         return;
        #     }

        #     items.push(...value.items);

        #     if (value.total > offset + value.count) {
        #         return fetchNextChunk(offset + value.count);
        #     }
        # };

        # await fetchNextChunk();

        # if (contentType === 'text/csv') {
        #     const value = stringify([
        #         Object.keys(items[0]),
        #         ...items.map((item) => Object.values(item)),
        #     ]);
        #     return kvStore.setValue(key, value, { contentType });
        # }

        # if (contentType === 'application/json') {
        #     return kvStore.setValue(key, items);
        # }

        # throw new Error(`Unsupported content type: ${contentType}`);

    async def get_info(self) -> Optional[Dict]:
        return await self._client.get()

    def iterate_items(
        self,
        *,
        offset: int = 0,
        limit: Optional[int] = None,
        clean: Optional[bool] = None,
        desc: Optional[bool] = None,
        fields: Optional[List[str]] = None,
        omit: Optional[List[str]] = None,
        unwind: Optional[str] = None,
        skip_empty: Optional[bool] = None,
        skip_hidden: Optional[bool] = None,
    ) -> AsyncIterator[Dict]:
        return self._client.iterate_items(
            offset=offset,
            limit=limit,
            clean=clean,
            desc=desc,
            fields=fields,
            omit=omit,
            unwind=unwind,
            skip_empty=skip_empty,
            skip_hidden=skip_hidden,
        )

    # TODO: Do map and reduce methods make sense in Python?

    async def drop(self) -> None:
        """TODO: docs."""
        # await this.client.delete();
        # const manager = StorageManager.getManager(Dataset, this.config);
        # manager.closeStorage(this);
        await self._client.delete()
        # TODO: Resolve circular imports...
        # await StorageManager.close_storage(StorageTypes.DATASET, self._id)
