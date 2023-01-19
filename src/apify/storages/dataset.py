import csv
import io
from typing import AsyncIterator, Dict, List, Optional, Union

from apify_client import ApifyClientAsync
from apify_client._utils import ListPage
from apify_client.clients import DatasetClientAsync

from .._types import JSONSerializable
from .._utils import _wrap_internal
from ..config import Configuration
from ..memory_storage import MemoryStorage
from ..memory_storage.resource_clients import DatasetClient
from .key_value_store import KeyValueStore
from .storage_manager import StorageManager


class Dataset:
    """TODO: docs."""

    _id: str
    _name: Optional[str]
    _client: Union[DatasetClientAsync, DatasetClient]
    _config: Configuration

    def __init__(self, id: str, name: Optional[str], client: Union[ApifyClientAsync, MemoryStorage]) -> None:
        """TODO: docs (constructor should be "internal")."""
        self.get_data = _wrap_internal(self._get_data_internal, self.get_data)  # type: ignore
        self.push_data = _wrap_internal(self._push_data_internal, self.push_data)  # type: ignore
        self.export_to_json = _wrap_internal(self._export_to_json_internal, self.export_to_json)  # type: ignore
        self.export_to_csv = _wrap_internal(self._export_to_csv_internal, self.export_to_csv)  # type: ignore
        self._id = id
        self._name = name
        self._client = client.dataset(self._id)
        self._config = Configuration.get_global_configuration()  # We always use the global config

    @classmethod
    async def _create_instance(cls, dataset_id_or_name: str, client: Union[ApifyClientAsync, MemoryStorage]) -> 'Dataset':
        dataset_client = client.dataset(dataset_id_or_name)
        dataset_info = await dataset_client.get()
        if not dataset_info:
            dataset_info = await client.datasets().get_or_create(name=dataset_id_or_name)

        return Dataset(dataset_info['id'], dataset_info.get('name'), client)

    @classmethod
    def _get_default_name(cls, config: Configuration) -> str:
        return config.default_dataset_id

    @classmethod
    async def push_data(cls, data: JSONSerializable) -> None:
        """TODO: docs."""
        dataset = await cls.open()
        return await dataset.push_data(data)

    async def _push_data_internal(self, data: JSONSerializable) -> None:
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
        # TODO: Implement the size chunking mechanism from crawlee...
        # limit = MAX_PAYLOAD_SIZE_BYTES - math.ceil(MAX_PAYLOAD_SIZE_BYTES * SAFETY_BUFFER_PERCENT)
        await self._client.push_items(data)

    @classmethod
    async def get_data(
        cls,
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
        """TODO: docs."""
        dataset = await cls.open()
        return await dataset.get_data(
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

    async def _get_data_internal(
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
        # TODO: Simulate the above error in Python and handle accordingly...
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

    async def export_to(
        self,
        key: str,
        *,
        to_key_value_store: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> None:
        """TODO: docs."""
        key_value_store = await KeyValueStore.open(to_key_value_store)
        items: List[Dict] = []
        limit = 1000
        offset = 0
        while True:
            list_items = await self._client.list_items(limit=limit, offset=offset)
            items.extend(list_items.items)
            if list_items.total <= offset + list_items.count:
                break
            offset += list_items.count

        if len(items) == 0:
            raise ValueError('Cannot export an empty dataset')

        if content_type == 'text/csv':
            output = io.StringIO()
            writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)  # TODO: Compare quoting behavior with TS impl
            writer.writerows([items[0].keys(), *[item.values() for item in items]])
            value = output.getvalue()
            return await key_value_store.set_value(key, value, content_type)

        if content_type == 'application/json':
            return await key_value_store.set_value(key, items)

        raise ValueError(f'Unsupported content type: {content_type}')

    @classmethod
    async def export_to_json(
        cls,
        key: str,
        *,
        from_dataset: Optional[str] = None,
        to_key_value_store: Optional[str] = None,
    ) -> None:
        """TODO: docs."""
        dataset = await cls.open(from_dataset)
        await dataset.export_to_json(key, to_key_value_store=to_key_value_store)

    async def _export_to_json_internal(
        self,
        key: str,
        *,
        from_dataset: Optional[str] = None,  # noqa: U100
        to_key_value_store: Optional[str] = None,
    ) -> None:
        await self.export_to(key, to_key_value_store=to_key_value_store, content_type='application/json')

    @classmethod
    async def export_to_csv(
        cls,
        key: str,
        *,
        from_dataset: Optional[str] = None,
        to_key_value_store: Optional[str] = None,
    ) -> None:
        """TODO: docs."""
        dataset = await cls.open(from_dataset)
        await dataset.export_to_csv(key, to_key_value_store=to_key_value_store)

    async def _export_to_csv_internal(
        self,
        key: str,
        *,
        from_dataset: Optional[str] = None,  # noqa: U100
        to_key_value_store: Optional[str] = None,
    ) -> None:
        await self.export_to(key, to_key_value_store=to_key_value_store, content_type='text/csv')

    async def get_info(self) -> Optional[Dict]:
        """TODO: docs."""
        return await self._client.get()

    def iterate_items(  # ~forEach in TS
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
        """TODO: docs."""
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

    async def drop(self) -> None:
        """TODO: docs."""
        await self._client.delete()
        await StorageManager.close_storage(self.__class__, self._id, self._name)

    @classmethod
    async def open(cls, dataset_id_or_name: Optional[str] = None, config: Optional[Configuration] = None) -> 'Dataset':
        """TODO: docs."""
        return await StorageManager.open_storage(cls, dataset_id_or_name, None, config)
