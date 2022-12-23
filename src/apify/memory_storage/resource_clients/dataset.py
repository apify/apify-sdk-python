import json
import os
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, AsyncGenerator, AsyncIterator, Dict, List, Optional, Tuple, Union

import aioshutil

from ..._types import JSONSerializable
from ..._utils import ListPage
from ..file_storage_utils import _update_dataset_items, _update_metadata
from ._utils import StorageTypes, _force_rename, _raise_on_duplicate_storage, _raise_on_non_existing_storage, uuid_regex

if TYPE_CHECKING:
    from ..memory_storage import MemoryStorage

"""
 Number of characters of the dataset item file names.
 E.g.: 000000019.json - 9 digits
"""
LOCAL_ENTRY_NAME_DIGITS = 9


class DatasetClient:
    """TODO: docs."""

    created_at = datetime.utcnow()
    accessed_at = datetime.utcnow()
    modified_at = datetime.utcnow()
    item_count = 0
    dataset_entries: Dict[str, Dict] = {}

    def __init__(self, *, base_storage_directory: str, client: 'MemoryStorage', id: Optional[str] = None, name: Optional[str] = None) -> None:
        """TODO: docs."""
        self.id = str(uuid.uuid4()) if id is None else id
        self.dataset_directory = os.path.join(base_storage_directory, name or self.id)
        self.client = client
        self.name = name

    async def get(self) -> Optional[Dict]:
        """TODO: docs."""
        found = _find_or_cache_dataset_by_possible_id(client=self.client, entry_name_or_id=self.name or self.id)

        if found:
            await found.update_timestamps(False)
            return found.to_dataset_info()

        return None

    async def update(self, *, name: Optional[str] = None) -> Dict:
        """TODO: docs."""
        # Check by id
        existing_store_by_id = _find_or_cache_dataset_by_possible_id(client=self.client, entry_name_or_id=self.name or self.id)

        if existing_store_by_id is None:
            _raise_on_non_existing_storage(StorageTypes.DATASET, self.id)

        # Skip if no changes
        if name is None:
            return existing_store_by_id.to_dataset_info()

        # Check that name is not in use already
        existing_store_by_name = next(
            (store for store in self.client.datasets_handled if store.name and store.name.lower() == name.lower()), None)

        if existing_store_by_name is not None:
            _raise_on_duplicate_storage(StorageTypes.DATASET, 'name', name)

        existing_store_by_id.name = name

        previous_dir = existing_store_by_id.dataset_directory

        existing_store_by_id.dataset_directory = os.path.join(self.client.datasets_directory, name)

        await _force_rename(previous_dir, existing_store_by_id.dataset_directory)

        # Update timestamps
        await existing_store_by_id.update_timestamps(True)

        return existing_store_by_id.to_dataset_info()

    async def delete(self) -> None:
        """TODO: docs."""
        store = next((store for store in self.client.datasets_handled if store.id == self.id), None)

        if store is not None:
            self.client.datasets_handled.remove(store)
            store.item_count = 0
            store.dataset_entries.clear()

            await aioshutil.rmtree(store.dataset_directory)

    async def list_items(
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
        """TODO: docs."""
        # Check by id
        existing_store_by_id = _find_or_cache_dataset_by_possible_id(client=self.client, entry_name_or_id=self.name or self.id)

        if existing_store_by_id is None:
            _raise_on_non_existing_storage(StorageTypes.DATASET, self.id)

        start, end = existing_store_by_id._get_start_and_end_indexes(
            max(existing_store_by_id.item_count - (offset or 0) - (limit or 0), 0) if desc else offset or 0,
            limit,
        )

        items = []

        for idx in range(start, end):
            entry_number = self._generate_local_entry_name(idx)
            items.append(existing_store_by_id.dataset_entries[entry_number])

        await existing_store_by_id.update_timestamps(False)

        if desc:
            items.reverse()

        return ListPage({
            'count': len(items),
            'desc': desc or False,
            'items': items,
            'limit': limit,
            'offset': offset,
            'total': existing_store_by_id.item_count,
        })

    async def iterate_items(
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
    ) -> AsyncGenerator:  # TODO: Copy-pasted from client
        """TODO: docs."""
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
                clean=clean,
                desc=desc,
                fields=fields,
                omit=omit,
                unwind=unwind,
                skip_empty=skip_empty,
                skip_hidden=skip_hidden,
            )

            current_offset += current_items_page.count
            if last_item is None or current_items_page.total < last_item:
                last_item = current_items_page.total

            for item in current_items_page.items:
                yield item

    async def get_items_as_bytes(
        self,
        *,
        item_format: str = 'json',
        offset: Optional[int] = None,
        limit: Optional[int] = None,
        desc: Optional[bool] = None,
        clean: Optional[bool] = None,
        bom: Optional[bool] = None,
        delimiter: Optional[str] = None,
        fields: Optional[List[str]] = None,
        omit: Optional[List[str]] = None,
        unwind: Optional[str] = None,
        skip_empty: Optional[bool] = None,
        skip_header_row: Optional[bool] = None,
        skip_hidden: Optional[bool] = None,
        xml_root: Optional[str] = None,
        xml_row: Optional[str] = None,
        flatten: Optional[List[str]] = None,
    ) -> bytes:
        """TODO: docs."""
        raise NotImplementedError('This method is not supported in local memory storage')

    async def stream_items(
        self,
        *,
        item_format: str = 'json',
        offset: Optional[int] = None,
        limit: Optional[int] = None,
        desc: Optional[bool] = None,
        clean: Optional[bool] = None,
        bom: Optional[bool] = None,
        delimiter: Optional[str] = None,
        fields: Optional[List[str]] = None,
        omit: Optional[List[str]] = None,
        unwind: Optional[str] = None,
        skip_empty: Optional[bool] = None,
        skip_header_row: Optional[bool] = None,
        skip_hidden: Optional[bool] = None,
        xml_root: Optional[str] = None,
        xml_row: Optional[str] = None,
    ) -> AsyncIterator:
        """TODO: docs."""
        raise NotImplementedError('This method is not supported in local memory storage')

    async def push_items(self, items: JSONSerializable) -> None:
        """TODO: docs."""
        # Check by id
        existing_store_by_id = _find_or_cache_dataset_by_possible_id(client=self.client, entry_name_or_id=self.name or self.id)

        if existing_store_by_id is None:
            _raise_on_non_existing_storage(StorageTypes.DATASET, self.id)

        normalized = self._normalize_items(items)

        added_ids: List[str] = []
        for entry in normalized:
            existing_store_by_id.item_count += 1
            idx = self._generate_local_entry_name(existing_store_by_id.item_count)

            existing_store_by_id.dataset_entries[idx] = entry
            added_ids.append(idx)

        data_entries: List[Tuple[str, Dict]] = []
        for id in added_ids:
            data_entries.append((id, existing_store_by_id.dataset_entries[id]))

        await existing_store_by_id.update_timestamps(True)

        await _update_dataset_items(
            data=data_entries,
            entity_directory=existing_store_by_id.dataset_directory,
            persist_storage=self.client.persist_storage,
        )

    def to_dataset_info(self) -> Dict:
        """TODO: docs."""
        return {
            'id': self.id,
            'name': self.name,
            'itemCount': self.item_count,
            'accessedAt': self.accessed_at,
            'createdAt': self.created_at,
            'modifiedAt': self.modified_at,
        }

    async def update_timestamps(self, has_been_modified: bool) -> None:
        """TODO: docs."""
        self.accessed_at = datetime.utcnow()

        if has_been_modified:
            self.modified_at = datetime.utcnow()

        dataset_info = self.to_dataset_info()
        await _update_metadata(data=dataset_info, entity_directory=self.dataset_directory, write_metadata=self.client.write_metadata)

    def _get_start_and_end_indexes(self, offset: int, limit: Optional[int] = None) -> Tuple[int, int]:
        actual_limit = limit or self.item_count
        start = offset + 1
        end = min(offset + actual_limit, self.item_count) + 1
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
    found = next((store for store in client.datasets_handled
                  if store.id == entry_name_or_id or (store.name and store.name.lower() == entry_name_or_id.lower())), None)

    if found is not None:
        return found

    datasets_dir = os.path.join(client.datasets_directory, entry_name_or_id)
    # Check if directory exists
    if not os.access(datasets_dir, os.F_OK):
        return None

    id: Union[str, None] = None
    name: Union[str, None] = None
    item_count = 0
    created_at = datetime.utcnow()
    accessed_at = datetime.utcnow()
    modified_at = datetime.utcnow()
    entries: Dict[str, Dict] = {}

    has_seen_metadata_file = False

    # Access the dataset folder
    for entry in os.scandir(datasets_dir):
        if entry.is_file():
            if entry.name == '__metadata__.json':
                has_seen_metadata_file = True

                # We have found the store metadata file, build out information based on it
                with open(os.path.join(datasets_dir, entry.name)) as f:
                    metadata = json.load(f)
                id = metadata['id']
                name = metadata['name']
                item_count = metadata['itemCount']
                created_at = datetime.strptime(metadata['createdAt'], '%Y-%m-%dT%H:%M:%S.%fZ')
                accessed_at = datetime.strptime(metadata['accessedAt'], '%Y-%m-%dT%H:%M:%S.%fZ')
                modified_at = datetime.strptime(metadata['modifiedAt'], '%Y-%m-%dT%H:%M:%S.%fZ')

                continue

            with open(os.path.join(datasets_dir, entry.name)) as f:
                entry_content = json.load(f)
            entry_name = entry.name.split('.')[0]

            entries[entry_name] = entry_content

            if not has_seen_metadata_file:
                item_count += 1

    if id is None and name is None:
        is_uuid = uuid_regex.match(entry_name_or_id)

        if is_uuid is not None:
            id = entry_name_or_id
        else:
            name = entry_name_or_id

    new_client = DatasetClient(base_storage_directory=client.datasets_directory, client=client, id=id, name=name)

    # Overwrite properties
    new_client.accessed_at = accessed_at
    new_client.created_at = created_at
    new_client.modified_at = modified_at
    new_client.item_count = item_count

    for entry_id, content in entries.items():
        new_client.dataset_entries[entry_id] = content

    client.datasets_handled.append(new_client)

    return new_client
