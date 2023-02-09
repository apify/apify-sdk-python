import json
import os
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List, Optional, Tuple, Union

import aioshutil

from apify_client._utils import ListPage

from ..._types import JSONSerializable
from ..._utils import _force_rename, _is_uuid, _raise_on_duplicate_storage, _raise_on_non_existing_storage
from ...consts import StorageTypes
from ..file_storage_utils import _update_dataset_items, _update_metadata

if TYPE_CHECKING:
    from ..memory_storage import MemoryStorage

"""
 This is what API returns in the x-apify-pagination-limit
 header when no limit query parameter is used.
 """
LIST_ITEMS_LIMIT = 999_999_999_999

"""
 Number of characters of the dataset item file names.
 E.g.: 000000019.json - 9 digits
"""
LOCAL_ENTRY_NAME_DIGITS = 9


class DatasetClient:
    """Sub-client for manipulating a single dataset."""

    _id: str
    _dataset_directory: str
    _client: 'MemoryStorage'
    _name: Optional[str]
    _dataset_entries: Dict[str, Dict]
    _created_at: datetime
    _accessed_at: datetime
    _modified_at: datetime
    _item_count = 0

    def __init__(self, *, base_storage_directory: str, client: 'MemoryStorage', id: Optional[str] = None, name: Optional[str] = None) -> None:
        """Initialize the DatasetClient."""
        self._id = str(uuid.uuid4()) if id is None else id
        self._dataset_directory = os.path.join(base_storage_directory, name or self._id)
        self._client = client
        self._name = name
        self._dataset_entries = {}
        self._created_at = datetime.now(timezone.utc)
        self._accessed_at = datetime.now(timezone.utc)
        self._modified_at = datetime.now(timezone.utc)

    async def get(self) -> Optional[Dict]:
        """Retrieve the dataset.

        Returns:
            dict, optional: The retrieved dataset, or None, if it does not exist
        """
        found = _find_or_cache_dataset_by_possible_id(client=self._client, entry_name_or_id=self._name or self._id)

        if found:
            await found._update_timestamps(False)
            return found.to_dataset_info()

        return None

    async def update(self, *, name: Optional[str] = None) -> Dict:
        """Update the dataset with specified fields.

        Args:
            name (str, optional): The new name for the dataset

        Returns:
            dict: The updated dataset
        """
        # Check by id
        existing_dataset_by_id = _find_or_cache_dataset_by_possible_id(client=self._client, entry_name_or_id=self._name or self._id)

        if existing_dataset_by_id is None:
            _raise_on_non_existing_storage(StorageTypes.DATASET, self._id)

        # Skip if no changes
        if name is None:
            return existing_dataset_by_id.to_dataset_info()

        # Check that name is not in use already
        existing_dataset_by_name = next(
            (dataset for dataset in self._client._datasets_handled if dataset._name and dataset._name.lower() == name.lower()), None)

        if existing_dataset_by_name is not None:
            _raise_on_duplicate_storage(StorageTypes.DATASET, 'name', name)

        existing_dataset_by_id._name = name

        previous_dir = existing_dataset_by_id._dataset_directory

        existing_dataset_by_id._dataset_directory = os.path.join(self._client._datasets_directory, name)

        await _force_rename(previous_dir, existing_dataset_by_id._dataset_directory)

        # Update timestamps
        await existing_dataset_by_id._update_timestamps(True)

        return existing_dataset_by_id.to_dataset_info()

    async def delete(self) -> None:
        """Delete the dataset."""
        dataset = next((dataset for dataset in self._client._datasets_handled if dataset._id == self._id), None)

        if dataset is not None:
            self._client._datasets_handled.remove(dataset)
            dataset._item_count = 0
            dataset._dataset_entries.clear()

            if os.path.exists(dataset._dataset_directory):
                await aioshutil.rmtree(dataset._dataset_directory)

    async def list_items(
        self,
        *,
        offset: Optional[int] = 0,
        limit: Optional[int] = LIST_ITEMS_LIMIT,
        clean: Optional[bool] = None,  # noqa: U100
        desc: Optional[bool] = None,
        fields: Optional[List[str]] = None,  # noqa: U100
        omit: Optional[List[str]] = None,  # noqa: U100
        unwind: Optional[str] = None,  # noqa: U100
        skip_empty: Optional[bool] = None,  # noqa: U100
        skip_hidden: Optional[bool] = None,  # noqa: U100
        flatten: Optional[List[str]] = None,  # noqa: U100
        view: Optional[str] = None,  # noqa: U100
    ) -> ListPage:
        """List the items of the dataset.

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
        # Check by id
        existing_dataset_by_id = _find_or_cache_dataset_by_possible_id(client=self._client, entry_name_or_id=self._name or self._id)

        if existing_dataset_by_id is None:
            _raise_on_non_existing_storage(StorageTypes.DATASET, self._id)

        start, end = existing_dataset_by_id._get_start_and_end_indexes(
            max(existing_dataset_by_id._item_count - (offset or 0) - (limit or LIST_ITEMS_LIMIT), 0) if desc else offset or 0,
            limit,
        )

        items = []

        for idx in range(start, end):
            entry_number = self._generate_local_entry_name(idx)
            items.append(existing_dataset_by_id._dataset_entries[entry_number])

        await existing_dataset_by_id._update_timestamps(False)

        if desc:
            items.reverse()

        return ListPage({
            'count': len(items),
            'desc': desc or False,
            'items': items,
            'limit': limit or LIST_ITEMS_LIMIT,
            'offset': offset or 0,
            'total': existing_dataset_by_id._item_count,
        })

    async def iterate_items(
        self,
        *,
        offset: int = 0,
        limit: Optional[int] = None,
        clean: Optional[bool] = None,  # noqa: U100
        desc: Optional[bool] = None,
        fields: Optional[List[str]] = None,  # noqa: U100
        omit: Optional[List[str]] = None,  # noqa: U100
        unwind: Optional[str] = None,  # noqa: U100
        skip_empty: Optional[bool] = None,  # noqa: U100
        skip_hidden: Optional[bool] = None,  # noqa: U100
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
        cache_size = 1000
        first_item = offset

        # If there is no limit, set last_item to None until we get the total from the first API response
        if limit is None:
            last_item = None
        else:
            last_item = offset + limit

        current_offset = first_item
        while last_item is None or current_offset < last_item:
            if last_item is None:
                current_limit = cache_size
            else:
                current_limit = min(cache_size, last_item - current_offset)

            current_items_page = await self.list_items(
                offset=current_offset,
                limit=current_limit,
                desc=desc,
            )

            current_offset += current_items_page.count
            if last_item is None or current_items_page.total < last_item:
                last_item = current_items_page.total

            for item in current_items_page.items:
                yield item

    async def get_items_as_bytes(self, *_args: Any, **_kwargs: Any) -> bytes:  # noqa: D102
        raise NotImplementedError('This method is not supported in local memory storage.')

    async def stream_items(self, *_args: Any, **_kwargs: Any) -> AsyncIterator:  # noqa: D102
        raise NotImplementedError('This method is not supported in local memory storage')

    async def push_items(self, items: JSONSerializable) -> None:
        """Push items to the dataset.

        Args:
            items: The items which to push in the dataset. Either a stringified JSON, a dictionary, or a list of strings or dictionaries.
        """
        # Check by id
        existing_dataset_by_id = _find_or_cache_dataset_by_possible_id(client=self._client, entry_name_or_id=self._name or self._id)

        if existing_dataset_by_id is None:
            _raise_on_non_existing_storage(StorageTypes.DATASET, self._id)

        normalized = self._normalize_items(items)

        added_ids: List[str] = []
        for entry in normalized:
            existing_dataset_by_id._item_count += 1
            idx = self._generate_local_entry_name(existing_dataset_by_id._item_count)

            existing_dataset_by_id._dataset_entries[idx] = entry
            added_ids.append(idx)

        data_entries: List[Tuple[str, Dict]] = []
        for id in added_ids:
            data_entries.append((id, existing_dataset_by_id._dataset_entries[id]))

        await existing_dataset_by_id._update_timestamps(True)

        await _update_dataset_items(
            data=data_entries,
            entity_directory=existing_dataset_by_id._dataset_directory,
            persist_storage=self._client._persist_storage,
        )

    def to_dataset_info(self) -> Dict:
        """Retrieve the dataset info."""
        return {
            'id': self._id,
            'name': self._name,
            'itemCount': self._item_count,
            'accessedAt': self._accessed_at,
            'createdAt': self._created_at,
            'modifiedAt': self._modified_at,
        }

    async def _update_timestamps(self, has_been_modified: bool) -> None:
        """Update the timestamps of the dataset."""
        self._accessed_at = datetime.now(timezone.utc)

        if has_been_modified:
            self._modified_at = datetime.now(timezone.utc)

        dataset_info = self.to_dataset_info()
        await _update_metadata(data=dataset_info, entity_directory=self._dataset_directory, write_metadata=self._client._write_metadata)

    def _get_start_and_end_indexes(self, offset: int, limit: Optional[int] = None) -> Tuple[int, int]:
        actual_limit = limit or self._item_count
        start = offset + 1
        end = min(offset + actual_limit, self._item_count) + 1
        return (start, end)

    def _generate_local_entry_name(self, idx: int) -> str:
        return str(idx).zfill(LOCAL_ENTRY_NAME_DIGITS)

    def _normalize_items(self, items: JSONSerializable) -> List[Dict]:
        def normalize_item(item: Any) -> Optional[Dict]:
            if type(item) is str:
                item = json.loads(item)

            if type(item) is list:
                received = ',\n'.join(item)
                raise ValueError(f'Each dataset item can only be a single JSON object, not an array. Received: [{received}]')

            if type(item) is not dict and item is not None:
                raise ValueError(f'Each dataset item must be a JSON object. Received: {item}')

            return item

        if type(items) is str:
            items = json.loads(items)

        result = list(map(normalize_item, items)) if type(items) is list else [normalize_item(items)]
        # filter(None, ..) returns items that are True
        return list(filter(None, result))


def _find_or_cache_dataset_by_possible_id(client: 'MemoryStorage', entry_name_or_id: str) -> Optional['DatasetClient']:
    # First check memory cache
    found = next((dataset for dataset in client._datasets_handled
                  if dataset._id == entry_name_or_id or (dataset._name and dataset._name.lower() == entry_name_or_id.lower())), None)

    if found is not None:
        return found

    datasets_dir = os.path.join(client._datasets_directory, entry_name_or_id)
    # Check if directory exists
    if not os.access(datasets_dir, os.F_OK):
        return None

    id: Union[str, None] = None
    name: Union[str, None] = None
    item_count = 0
    created_at = datetime.now(timezone.utc)
    accessed_at = datetime.now(timezone.utc)
    modified_at = datetime.now(timezone.utc)
    entries: Dict[str, Dict] = {}

    has_seen_metadata_file = False

    # Access the dataset folder
    for entry in os.scandir(datasets_dir):
        if entry.is_file():
            if entry.name == '__metadata__.json':
                has_seen_metadata_file = True

                # We have found the dataset's metadata file, build out information based on it
                with open(os.path.join(datasets_dir, entry.name)) as f:
                    metadata = json.load(f)
                id = metadata['id']
                name = metadata['name']
                item_count = metadata['itemCount']
                created_at = datetime.fromisoformat(metadata['createdAt'])
                accessed_at = datetime.fromisoformat(metadata['accessedAt'])
                modified_at = datetime.fromisoformat(metadata['modifiedAt'])

                continue

            with open(os.path.join(datasets_dir, entry.name)) as f:
                entry_content = json.load(f)
            entry_name = entry.name.split('.')[0]

            entries[entry_name] = entry_content

            if not has_seen_metadata_file:
                item_count += 1

    if id is None and name is None:
        is_uuid = _is_uuid(entry_name_or_id)

        if is_uuid:
            id = entry_name_or_id
        else:
            name = entry_name_or_id

    new_client = DatasetClient(base_storage_directory=client._datasets_directory, client=client, id=id, name=name)

    # Overwrite properties
    new_client._accessed_at = accessed_at
    new_client._created_at = created_at
    new_client._modified_at = modified_at
    new_client._item_count = item_count

    for entry_id, content in entries.items():
        new_client._dataset_entries[entry_id] = content

    client._datasets_handled.append(new_client)

    return new_client
