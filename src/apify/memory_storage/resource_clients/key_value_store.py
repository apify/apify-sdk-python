import io
import json
import mimetypes
import os
import pathlib
import uuid
import warnings
from datetime import datetime
from operator import itemgetter
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, Optional, Union

import aioshutil

from ..._utils import (
    _force_rename,
    _guess_file_extension,
    _is_file_or_bytes,
    _is_uuid,
    _json_dumps,
    _maybe_parse_body,
    _raise_on_duplicate_storage,
    _raise_on_non_existing_storage,
)
from ...consts import DEFAULT_API_PARAM_LIMIT, StorageTypes
from ..file_storage_utils import _set_or_delete_key_value_store_record, _update_metadata

if TYPE_CHECKING:
    from ..memory_storage import MemoryStorage

DEFAULT_LOCAL_FILE_EXTENSION = 'bin'


class KeyValueStoreClient:
    """TODO: docs."""

    _id: str
    _key_value_store_directory: str
    _client: 'MemoryStorage'
    _name: Optional[str]
    _key_value_entries: Dict[str, Dict]
    _created_at: datetime
    _accessed_at: datetime
    _modified_at: datetime

    def __init__(self, *, base_storage_directory: str, client: 'MemoryStorage', id: Optional[str] = None, name: Optional[str] = None) -> None:
        """TODO: docs."""
        self._id = str(uuid.uuid4()) if id is None else id
        self._key_value_store_directory = os.path.join(base_storage_directory, name or self._id)
        self._client = client
        self._name = name
        self._key_value_entries = {}
        self._created_at = datetime.utcnow()
        self._accessed_at = datetime.utcnow()
        self._modified_at = datetime.utcnow()

    async def get(self) -> Optional[Dict]:
        """TODO: docs."""
        found = _find_or_cache_key_value_store_by_possible_id(client=self._client, entry_name_or_id=self._name or self._id)

        if found:
            await found._update_timestamps(False)
            return found.to_key_value_store_info()

        return None

    async def update(self, *, name: Optional[str] = None) -> Dict:
        """TODO: docs."""
        # Check by id
        existing_store_by_id = _find_or_cache_key_value_store_by_possible_id(client=self._client, entry_name_or_id=self._name or self._id)

        if existing_store_by_id is None:
            _raise_on_non_existing_storage(StorageTypes.KEY_VALUE_STORE, self._id)

        # Skip if no changes
        if name is None:
            return existing_store_by_id.to_key_value_store_info()

        # Check that name is not in use already
        existing_store_by_name = next(
            (store for store in self._client._key_value_stores_handled if store._name and store._name.lower() == name.lower()), None)

        if existing_store_by_name is not None:
            _raise_on_duplicate_storage(StorageTypes.KEY_VALUE_STORE, 'name', name)

        existing_store_by_id._name = name

        previous_dir = existing_store_by_id._key_value_store_directory

        existing_store_by_id._key_value_store_directory = os.path.join(self._client._key_value_stores_directory, name)

        await _force_rename(previous_dir, existing_store_by_id._key_value_store_directory)

        # Update timestamps
        await existing_store_by_id._update_timestamps(True)

        return existing_store_by_id.to_key_value_store_info()

    async def delete(self) -> None:
        """TODO: docs."""
        store = next((store for store in self._client._key_value_stores_handled if store._id == self._id), None)

        if store is not None:
            self._client._key_value_stores_handled.remove(store)
            store._key_value_entries.clear()

            if os.path.exists(store._key_value_store_directory):
                await aioshutil.rmtree(store._key_value_store_directory)

    async def list_keys(self, *, limit: int = DEFAULT_API_PARAM_LIMIT, exclusive_start_key: Optional[str] = None) -> Dict:
        """TODO: docs."""
        # Check by id
        existing_store_by_id = _find_or_cache_key_value_store_by_possible_id(self._client, self._name or self._id)

        if existing_store_by_id is None:
            _raise_on_non_existing_storage(StorageTypes.KEY_VALUE_STORE, self._id)

        items = []

        for record in existing_store_by_id._key_value_entries.values():
            size = len(record['value'])
            items.append({
                'key': record['key'],
                'size': size,
            })

        if len(items) == 0:
            return {
                'count': len(items),
                'limit': limit,
                'exclusiveStartKey': exclusive_start_key,
                'isTruncated': False,
                'nextExclusiveStartKey': None,
                'items': items,
            }

        # Lexically sort to emulate the API
        items = sorted(items, key=itemgetter('key'))

        truncated_items = items
        if exclusive_start_key is not None:
            key_pos = next((idx for idx, i in enumerate(items) if i['key'] == exclusive_start_key), None)
            if key_pos is not None:
                truncated_items = items[key_pos + 1:]

        limited_items = truncated_items[:limit]

        last_item_in_store = items[-1]
        last_selected_item = limited_items[-1]
        is_last_selected_item_absolutely_last = last_item_in_store == last_selected_item
        next_exclusive_start_key = None if is_last_selected_item_absolutely_last else last_selected_item['key']

        await existing_store_by_id._update_timestamps(False)

        return {
            'count': len(items),
            'limit': limit,
            'exclusiveStartKey': exclusive_start_key,
            'isTruncated': not is_last_selected_item_absolutely_last,
            'nextExclusiveStartKey': next_exclusive_start_key,
            'items': limited_items,
        }

    async def _get_record_internal(self, key: str, as_bytes: bool = False) -> Optional[Dict]:
        # Check by id
        existing_store_by_id = _find_or_cache_key_value_store_by_possible_id(self._client, self._name or self._id)

        if existing_store_by_id is None:
            _raise_on_non_existing_storage(StorageTypes.KEY_VALUE_STORE, self._id)

        entry = existing_store_by_id._key_value_entries.get(key)

        if entry is None:
            return None

        record = {
            'key': entry['key'],
            'value': entry['value'],
            # To guess the type, we need a real file name, not just the extension. e.g. 'file.json' instead of 'json'
            'contentType': entry.get('content_type') or mimetypes.guess_type(f"file.{entry['extension']}")[0],
        }

        if not as_bytes:
            record['value'] = _maybe_parse_body(record['value'], record['contentType'])

        await existing_store_by_id._update_timestamps(False)

        return record

    async def get_record(self, key: str) -> Optional[Dict]:
        """TODO: docs."""
        return await self._get_record_internal(key)

    async def get_record_as_bytes(self, key: str) -> Optional[Dict]:
        """TODO: docs."""
        return await self._get_record_internal(key, as_bytes=True)

    async def stream_record(self, _key: str) -> AsyncIterator[Optional[Dict]]:
        """TODO: docs."""
        raise NotImplementedError('This method is not supported in local memory storage')

    async def set_record(self, key: str, value: Any, content_type: Optional[str] = None) -> None:
        """TODO: docs."""
        # Check by id
        existing_store_by_id = _find_or_cache_key_value_store_by_possible_id(self._client, self._name or self._id)

        if existing_store_by_id is None:
            _raise_on_non_existing_storage(StorageTypes.KEY_VALUE_STORE, self._id)

        if isinstance(value, io.IOBase):
            raise NotImplementedError('File-like values are not supported in local memory storage')

        if content_type is None:
            if _is_file_or_bytes(value):
                content_type = 'application/octet-stream'
            elif isinstance(value, str):
                content_type = 'text/plain; charset=utf-8'
            else:
                content_type = 'application/json; charset=utf-8'

        extension = _guess_file_extension(content_type or '') or DEFAULT_LOCAL_FILE_EXTENSION

        if 'application/json' in content_type and not _is_file_or_bytes(value) and not isinstance(value, str):
            value = _json_dumps(value).encode('utf-8')

        record = {
            'extension': extension,
            'key': key,
            'value': value,
            'content_type': content_type,
        }

        existing_store_by_id._key_value_entries[key] = record

        await existing_store_by_id._update_timestamps(True)
        await _set_or_delete_key_value_store_record(
            entity_directory=existing_store_by_id._key_value_store_directory,
            persist_storage=self._client._persist_storage,
            record=record,
            should_set=True,
            write_metadata=self._client._write_metadata,
        )

    async def delete_record(self, key: str) -> None:
        """TODO: docs."""
        # Check by id
        existing_store_by_id = _find_or_cache_key_value_store_by_possible_id(self._client, self._name or self._id)

        if existing_store_by_id is None:
            _raise_on_non_existing_storage(StorageTypes.KEY_VALUE_STORE, self._id)

        entry = existing_store_by_id._key_value_entries.get(key)

        if entry is not None:
            del existing_store_by_id._key_value_entries[key]
            await existing_store_by_id._update_timestamps(True)
            await _set_or_delete_key_value_store_record(
                entity_directory=existing_store_by_id._key_value_store_directory,
                persist_storage=self._client._persist_storage,
                record=entry,
                should_set=False,
                write_metadata=self._client._write_metadata,
            )

    def to_key_value_store_info(self) -> Dict:
        """TODO: docs."""
        return {
            'id': self._id,
            'name': self._name,
            'accessedAt': self._accessed_at,
            'createdAt': self._created_at,
            'modifiedAt': self._modified_at,
            'userId': '1',
        }

    async def _update_timestamps(self, has_been_modified: bool) -> None:
        """TODO: docs."""
        self._accessed_at = datetime.utcnow()

        if has_been_modified:
            self._modified_at = datetime.utcnow()

        kv_store_info = self.to_key_value_store_info()
        await _update_metadata(data=kv_store_info, entity_directory=self._key_value_store_directory, write_metadata=self._client._write_metadata)


def _find_or_cache_key_value_store_by_possible_id(client: 'MemoryStorage', entry_name_or_id: str) -> Optional['KeyValueStoreClient']:
    # First check memory cache
    found = next((store for store in client._key_value_stores_handled
                  if store._id == entry_name_or_id or (store._name and store._name.lower() == entry_name_or_id.lower())), None)

    if found is not None:
        return found

    key_value_store_dir = os.path.join(client._key_value_stores_directory, entry_name_or_id)
    # Check if directory exists
    if not os.access(key_value_store_dir, os.F_OK):
        return None

    id: Union[str, None] = None
    name: Union[str, None] = None
    created_at = datetime.utcnow()
    accessed_at = datetime.utcnow()
    modified_at = datetime.utcnow()
    internal_records: Dict[str, Dict] = {}

    # Access the key value store folder
    for entry in os.scandir(key_value_store_dir):
        if entry.is_file():
            if entry.name == '__metadata__.json':
                # We have found the store metadata file, build out information based on it
                with open(os.path.join(key_value_store_dir, entry.name), encoding='utf8') as f:
                    metadata = json.load(f)
                id = metadata['id']
                name = metadata['name']
                created_at = datetime.strptime(metadata['createdAt'], '%Y-%m-%dT%H:%M:%S.%fZ')
                accessed_at = datetime.strptime(metadata['accessedAt'], '%Y-%m-%dT%H:%M:%S.%fZ')
                modified_at = datetime.strptime(metadata['modifiedAt'], '%Y-%m-%dT%H:%M:%S.%fZ')

                continue

            if '.__metadata__.' in entry.name:
                # This is an entry's metadata file, we can use it to create/extend the record
                with open(os.path.join(key_value_store_dir, entry.name), encoding='utf8') as f:
                    metadata = json.load(f)

                new_record = {
                    **internal_records.get(metadata['key'], {}),
                    **metadata,
                }

                internal_records[metadata['key']] = new_record

                continue

            with open(os.path.join(key_value_store_dir, entry.name), 'rb') as f:
                file_content = f.read()
            file_extension = pathlib.Path(entry.name).suffix
            content_type, _ = mimetypes.guess_type(entry.name)
            if content_type is None:
                content_type = 'text/plain'
            extension = _guess_file_extension(content_type)

            if file_extension == '':
                # We need to override and then restore the warnings filter so that the warning gets printed out,
                # Otherwise it would be silently swallowed
                with warnings.catch_warnings():
                    warnings.simplefilter('always')
                    warnings.warn(
                        f"""Key-value entry "{entry.name}" for store {entry_name_or_id} does not have a file extension, assuming it as text.
                        If you want to have correct interpretation of the file, you should add a file extension to the entry.""",
                        Warning,
                        stacklevel=2,
                    )
            elif 'application/json' in content_type:
                try:
                    # Try parsing the JSON ahead of time (not ideal but solves invalid files being loaded into stores)
                    json.loads(file_content)
                except json.JSONDecodeError:
                    # We need to override and then restore the warnings filter so that the warning gets printed out,
                    # Otherwise it would be silently swallowed
                    with warnings.catch_warnings():
                        warnings.simplefilter('always')
                        warnings.warn(
                            (f'Key-value entry "{entry.name}" for store {entry_name_or_id} has invalid JSON content'
                             'and will be ignored from the store.'),
                            Warning,
                            stacklevel=2,
                        )
                    continue

            name_split = entry.name.split('.')

            if file_extension != '':
                name_split.pop()

            key = '.'.join(name_split)

            new_record = {
                'key': key,
                'extension': extension,
                'value': file_content,
                'content_type': content_type,
                **internal_records.get(key, {}),
            }

            internal_records[key] = new_record

    if id is None and name is None:
        is_uuid = _is_uuid(entry_name_or_id)

        if is_uuid:
            id = entry_name_or_id
        else:
            name = entry_name_or_id

    new_client = KeyValueStoreClient(base_storage_directory=client._key_value_stores_directory, client=client, id=id, name=name)

    # Overwrite properties
    new_client._accessed_at = accessed_at
    new_client._created_at = created_at
    new_client._modified_at = modified_at

    for key, record in internal_records.items():
        new_client._key_value_entries[key] = record

    client._key_value_stores_handled.append(new_client)

    return new_client
