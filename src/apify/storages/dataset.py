
from typing import Any, Dict, Optional, TypedDict, TypeVar, Union, overload

from apify_client import ApifyClientAsync
from apify_client.clients import DatasetClientAsync

from .._types import JSONSerializable
from ..config import Configuration
from ..memory_storage import MemoryStorage
from ..memory_storage.resource_clients import DatasetClient
from ._utils import _purge_default_storages

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
    async def open(cls, store_id_or_name: str, client: Union[ApifyClientAsync, MemoryStorage], config: Configuration) -> 'Dataset':
        if config.purge_on_start:
            await _purge_default_storages(client)

        dataset_client = client.dataset(store_id_or_name)
        dataset_info = await dataset_client.get()
        if not dataset_info:
            dataset_info = await client.datasets().get_or_create(name=store_id_or_name)

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
        await self._client.push_items(data)
