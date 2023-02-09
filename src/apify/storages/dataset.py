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
    """The `Dataset` class represents a store for structured data where each object stored has the same attributes.

    You can imagine it as a table, where each object is a row and its attributes are columns.
    Dataset is an append-only storage - you can only add new records to it but you cannot modify or remove existing records.
    Typically it is used to store crawling results.

    Do not instantiate this class directly, use the `Actor.open_dataset()` function instead.

    `Dataset` stores its data either on local disk or in the Apify cloud,
    depending on whether the `APIFY_LOCAL_STORAGE_DIR` or `APIFY_TOKEN` environment variables are set.

    If the `APIFY_LOCAL_STORAGE_DIR` environment variable is set, the data is stored in
    the local directory in the following files:
    ```
    {APIFY_LOCAL_STORAGE_DIR}/datasets/{DATASET_ID}/{INDEX}.json
    ```
    Note that `{DATASET_ID}` is the name or ID of the dataset. The default dataset has ID: `default`,
    unless you override it by setting the `APIFY_DEFAULT_DATASET_ID` environment variable.
    Each dataset item is stored as a separate JSON file, where `{INDEX}` is a zero-based index of the item in the dataset.

    If the `APIFY_TOKEN` environment variable is set but `APIFY_LOCAL_STORAGE_DIR` is not, the data is stored in the
    [Apify Dataset](https://docs.apify.com/storage/dataset) cloud storage.
    """

    _id: str
    _name: Optional[str]
    _client: Union[DatasetClientAsync, DatasetClient]

    def __init__(self, id: str, name: Optional[str], client: Union[ApifyClientAsync, MemoryStorage]) -> None:
        """Create a `Dataset` instance.

        Do not use the constructor directly, use the `Actor.open_dataset()` function instead.

        Args:
            id (str): ID of the dataset.
            name (str, optional): Name of the dataset.
            client (ApifyClientAsync or MemoryStorage): The storage client which should be used.
        """
        self.get_data = _wrap_internal(self._get_data_internal, self.get_data)  # type: ignore
        self.push_data = _wrap_internal(self._push_data_internal, self.push_data)  # type: ignore
        self.export_to_json = _wrap_internal(self._export_to_json_internal, self.export_to_json)  # type: ignore
        self.export_to_csv = _wrap_internal(self._export_to_csv_internal, self.export_to_csv)  # type: ignore
        self._id = id
        self._name = name
        self._client = client.dataset(self._id)

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
        """Store an object or an array of objects to the dataset.

        The size of the data is limited by the receiving API and therefore `push_data()` will only
        allow objects whose JSON representation is smaller than 9MB. When an array is passed,
        none of the included objects may be larger than 9MB, but the array itself may be of any size.

        Args:
            data (JSONSerializable): dict or array of dicts containing data to be stored in the default dataset.
                The JSON representation of each item must be smaller than 9MB.
        """
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
        """Get items from the dataset.

        Args:
            offset (int, optional): Number of items that should be skipped at the start. The default value is 0
            limit (int, optional): Maximum number of items to return. By default there is no limit.
            desc (bool, optional): By default, results are returned in the same order as they were stored.
                To reverse the order, set this parameter to True.
            clean (bool, optional): If True, returns only non-empty items and skips hidden fields (i.e. fields starting with the # character).
                The clean parameter is just a shortcut for skip_hidden=True and skip_empty=True parameters.
                Note that since some objects might be skipped from the output, that the result might contain less items than the limit value.
            fields (list of str, optional): A list of fields which should be picked from the items,
                only these fields will remain in the resulting record objects.
                Note that the fields in the outputted items are sorted the same way as they are specified in the fields parameter.
                You can use this feature to effectively fix the output format.
            omit (list of str, optional): A list of fields which should be omitted from the items.
            unwind (str, optional): Name of a field which should be unwound.
                If the field is an array then every element of the array will become a separate record and merged with parent object.
                If the unwound field is an object then it is merged with the parent object.
                If the unwound field is missing or its value is neither an array nor an object and therefore cannot be merged with a parent object,
                then the item gets preserved as it is. Note that the unwound items ignore the desc parameter.
            skip_empty (bool, optional): If True, then empty items are skipped from the output.
                Note that if used, the results might contain less items than the limit value.
            skip_hidden (bool, optional): If True, then hidden fields are skipped from the output, i.e. fields starting with the # character.
            flatten (list of str, optional): A list of fields that should be flattened
            view (str, optional): Name of the dataset view to be used

        Returns:
            ListPage: A page of the list of dataset items according to the specified filters.
        """
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
        """Save the entirety of the dataset's contents into one file within a key-value store.

        Args:
            key (str): The key to save the data under.
            to_key_value_store (str, optional): The name of the key-value store in which the result will be saved.
                Uses default key-value store if omitted.
            content_type (str, optional): Either 'text/csv' or 'application/json'. Defaults to JSON.
        """
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
            writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
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
        """Save the entirety of the dataset's contents into one JSON file within a key-value store.

        Args:
            key (str): The key to save the data under.
            from_dataset (str, optional): The source dataset in case of calling the class method. Uses default dataset if omitted.
            to_key_value_store (str, optional): The name of the key-value store in which the result will be saved.
                Uses default key-value store if omitted.
        """
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
        """Save the entirety of the dataset's contents into one CSV file within a key-value store.

        Args:
            key (str): The key to save the data under.
            from_dataset (str, optional): The source dataset in case of calling the class method. Uses default dataset if omitted.
            to_key_value_store (str, optional): The name of the key-value store in which the result will be saved.
                Uses default key-value store if omitted.
        """
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
        """Get an object containing general information about the dataset.

        Returns:
            dict: Object returned by calling the GET dataset API endpoint.
        """
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
        """Iterate over the items in the dataset.

        Args:
            offset (int, optional): Number of items that should be skipped at the start. The default value is 0
            limit (int, optional): Maximum number of items to return. By default there is no limit.
            desc (bool, optional): By default, results are returned in the same order as they were stored.
                To reverse the order, set this parameter to True.
            clean (bool, optional): If True, returns only non-empty items and skips hidden fields (i.e. fields starting with the # character).
                The clean parameter is just a shortcut for skip_hidden=True and skip_empty=True parameters.
                Note that since some objects might be skipped from the output, that the result might contain less items than the limit value.
            fields (list of str, optional): A list of fields which should be picked from the items,
                only these fields will remain in the resulting record objects.
                Note that the fields in the outputted items are sorted the same way as they are specified in the fields parameter.
                You can use this feature to effectively fix the output format.
            omit (list of str, optional): A list of fields which should be omitted from the items.
            unwind (str, optional): Name of a field which should be unwound.
                If the field is an array then every element of the array will become a separate record and merged with parent object.
                If the unwound field is an object then it is merged with the parent object.
                If the unwound field is missing or its value is neither an array nor an object and therefore cannot be merged with a parent object,
                then the item gets preserved as it is. Note that the unwound items ignore the desc parameter.
            skip_empty (bool, optional): If True, then empty items are skipped from the output.
                Note that if used, the results might contain less items than the limit value.
            skip_hidden (bool, optional): If True, then hidden fields are skipped from the output, i.e. fields starting with the # character.

        Yields:
            dict: An item from the dataset
        """
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
        """Remove the dataset either from the Apify cloud storage or from the local directory."""
        await self._client.delete()
        await StorageManager.close_storage(self.__class__, self._id, self._name)

    @classmethod
    async def open(cls, dataset_id_or_name: Optional[str] = None, config: Optional[Configuration] = None) -> 'Dataset':
        """Open a dataset.

        Datasets are used to store structured data where each object stored has the same attributes,
        such as online store products or real estate offers.
        The actual data is stored either on the local filesystem or in the Apify cloud.

        Args:
            dataset_id_or_name (str, optional): ID or name of the dataset to be opened.
                If not provided, the method returns the default dataset associated with the actor run.
            config (Configuration, optional): A `Configuration` instance, uses global configuration if omitted.

        Returns:
            Dataset: An instance of the `Dataset` class for the given ID or name.

        """
        return await StorageManager.open_storage(cls, dataset_id_or_name, None, config)
