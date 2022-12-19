import json
import mimetypes
import os
import pathlib
import uuid
import warnings
from contextlib import asynccontextmanager
from datetime import datetime
from operator import itemgetter
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, Optional, Union

import aioshutil

from ..._utils import _json_serializer
from ...consts import DEFAULT_API_PARAM_LIMIT, StorageTypes
from ..file_storage_utils import _set_or_delete_key_value_store_record, _update_metadata
from ._utils import _guess_file_extension, _is_file_or_bytes, _maybe_parse_body, _raise_on_duplicate_entry, _raise_on_non_existing, uuid_regex

if TYPE_CHECKING:
    from ..memory_storage import MemoryStorage

DEFAULT_LOCAL_FILE_EXTENSION = 'bin'


class KeyValueStoreClient:
    """TODO: docs."""

    created_at = datetime.utcnow()
    accessed_at = datetime.utcnow()
    modified_at = datetime.utcnow()
    key_value_entries: Dict[str, Dict] = {}

    def __init__(self, *, base_storage_directory: str, client: 'MemoryStorage', id: Optional[str] = None, name: Optional[str] = None) -> None:
        """TODO: docs."""
        self.id = str(uuid.uuid4()) if id is None else id
        self.key_value_store_directory = os.path.join(base_storage_directory, name or self.id)
        self.client = client
        self.name = name

    async def get(self) -> Optional[Dict]:
        """TODO: docs."""
        found = _find_or_cache_key_value_store_by_possible_id(client=self.client, entry_name_or_id=self.name or self.id)

        if found:
            await found.update_timestamps(False)
            return found.to_key_value_store_info()

        return None

    async def update(self, *, name: Optional[str] = None) -> Dict:
        """TODO: docs."""
        # Check by id
        existing_store_by_id = _find_or_cache_key_value_store_by_possible_id(client=self.client, entry_name_or_id=self.name or self.id)

        if existing_store_by_id is None:
            _raise_on_non_existing(StorageTypes.KEY_VALUE_STORE, self.id)

        # Skip if no changes
        if name is None:
            return existing_store_by_id.to_key_value_store_info()

        # Check that name is not in use already
        existing_store_by_name = next(
            (store for store in self.client.key_value_stores_handled if store.name and store.name.lower() == name.lower()), None)

        if existing_store_by_name is not None:
            _raise_on_duplicate_entry(StorageTypes.KEY_VALUE_STORE, 'name', name)

        existing_store_by_id.name = name

        previous_dir = existing_store_by_id.key_value_store_directory

        existing_store_by_id.key_value_store_directory = os.path.join(self.client.key_value_stores_directory, name)

        # Remove new directory if it exists
        # TODO: compare to using os.renames, which has problems when target dir exists
        # TODO: check if ignore errors needed...
        await aioshutil.rmtree(existing_store_by_id.key_value_store_directory, ignore_errors=True)
        # Copy the previous directory to the new one
        await aioshutil.copytree(previous_dir, existing_store_by_id.key_value_store_directory)
        # Remove the previous directory
        await aioshutil.rmtree(previous_dir)

        # Update timestamps
        await existing_store_by_id.update_timestamps(True)

        return existing_store_by_id.to_key_value_store_info()

    async def delete(self) -> None:
        """TODO: docs."""
        store = next((store for store in self.client.key_value_stores_handled if store.id == self.id), None)

        if store is not None:
            self.client.key_value_stores_handled.remove(store)
            store.key_value_entries.clear()

            await aioshutil.rmtree(store.key_value_store_directory)

    async def list_keys(self, *, limit: int = DEFAULT_API_PARAM_LIMIT, exclusive_start_key: Optional[str] = None) -> Dict:
        """TODO: docs."""
        # Check by id
        existing_store_by_id = _find_or_cache_key_value_store_by_possible_id(self.client, self.name or self.id)

        if existing_store_by_id is None:
            _raise_on_non_existing(StorageTypes.KEY_VALUE_STORE, self.id)

        items = []

        for record in existing_store_by_id.key_value_entries.values():
            size = len(record['value'])  # TODO: Check if this works for all cases
            items.append({
                'key': record['key'],
                'size': size,
            })

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

        await existing_store_by_id.update_timestamps(False)

        return {
            'count': len(items),
            'limit': limit,
            'exclusiveStartKey': exclusive_start_key,
            'isTruncated': not is_last_selected_item_absolutely_last,
            'nextExclusiveStartKey': next_exclusive_start_key,
            'items': limited_items,
        }

    async def get_record(self, key: str) -> Optional[Dict]:
        """TODO: docs."""
        # Check by id
        existing_store_by_id = _find_or_cache_key_value_store_by_possible_id(self.client, self.name or self.id)

        if existing_store_by_id is None:
            _raise_on_non_existing(StorageTypes.KEY_VALUE_STORE, self.id)

        entry = existing_store_by_id.key_value_entries.get(key)

        if entry is None:
            return None

        record = {
            'key': entry['key'],
            'value': entry['value'],
            # To guess the type, we need a real file name, not just the extension. e.g. 'file.json' instead of 'json'
            'contentType': entry.get('content_type') or mimetypes.guess_type(f"file.{entry['extension']}")[0],  # TODO: Default value?
        }

        record['value'] = _maybe_parse_body(record['value'], record['contentType'])

        await existing_store_by_id.update_timestamps(False)

        return record

    async def get_record_as_bytes(self, key: str) -> Optional[Dict]:
        """TODO: docs."""
        # TODO: make a private method that reuses code instead of copy pasting get_record and removing one line with parsing ;)
        # Check by id
        existing_store_by_id = _find_or_cache_key_value_store_by_possible_id(self.client, self.name or self.id)

        if existing_store_by_id is None:
            _raise_on_non_existing(StorageTypes.KEY_VALUE_STORE, self.id)

        entry = existing_store_by_id.key_value_entries.get(key)

        if entry is None:
            return None

        record = {
            'key': entry['key'],
            'value': entry['value'],
            # To guess the type, we need a real file name, not just the extension. e.g. 'file.json' instead of 'json'
            'contentType': entry.get('content_type') or mimetypes.guess_type(f"file.{entry['extension']}")[0],  # TODO: Default value?
        }

        await existing_store_by_id.update_timestamps(False)

        return record

    @asynccontextmanager
    async def stream_record(self, key: str) -> AsyncIterator[Optional[Dict]]:
        """TODO: docs."""
        # TODO: implement - no idea how atm
        yield None

    async def set_record(self, key: str, value: Any, content_type: Optional[str] = None) -> None:
        """TODO: docs."""
        # Check by id
        existing_store_by_id = _find_or_cache_key_value_store_by_possible_id(self.client, self.name or self.id)

        if existing_store_by_id is None:
            _raise_on_non_existing(StorageTypes.KEY_VALUE_STORE, self.id)

        if content_type is None:
            if _is_file_or_bytes(value):
                content_type = 'application/octet-stream'
            elif isinstance(value, str):
                content_type = 'text/plain; charset=utf-8'
            else:
                content_type = 'application/json; charset=utf-8'

        extension = _guess_file_extension(content_type or '') or DEFAULT_LOCAL_FILE_EXTENSION

        if 'application/json' in content_type and not _is_file_or_bytes(value) and not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False, indent=2, default=_json_serializer).encode('utf-8')

        # TODO: Add stream support for this method...
        # if (valueIsStream) {
        #     const chunks = [];
        #     for await (const chunk of value) {
        #         chunks.push(chunk);
        #     }
        #     value = Buffer.concat(chunks);
        # }

        record = {
            'extension': extension,
            'key': key,
            'value': value,
            'content_type': content_type,
        }

        existing_store_by_id.key_value_entries[key] = record

        await existing_store_by_id.update_timestamps(True)
        await _set_or_delete_key_value_store_record(
            entity_directory=existing_store_by_id.key_value_store_directory,
            persist_storage=self.client.persist_storage,
            record=record,
            should_set=True,
            write_metadata=self.client.write_metadata,
        )

    async def delete_record(self, key: str) -> None:
        """TODO: docs."""
        # Check by id
        existing_store_by_id = _find_or_cache_key_value_store_by_possible_id(self.client, self.name or self.id)

        if existing_store_by_id is None:
            _raise_on_non_existing(StorageTypes.KEY_VALUE_STORE, self.id)

        entry = existing_store_by_id.key_value_entries.get(key)

        if entry is not None:
            del existing_store_by_id.key_value_entries[key]
            await existing_store_by_id.update_timestamps(True)
            await _set_or_delete_key_value_store_record(
                entity_directory=existing_store_by_id.key_value_store_directory,
                persist_storage=self.client.persist_storage,
                record=entry,
                should_set=False,
                write_metadata=self.client.write_metadata,
            )

    def to_key_value_store_info(self) -> Dict:
        """TODO: docs."""
        return {
            'id': self.id,
            'name': self.name,
            'accessedAt': self.accessed_at,
            'createdAt': self.created_at,
            'modifiedAt': self.modified_at,
            'userId': '1',
        }

    async def update_timestamps(self, has_been_modified: bool) -> None:
        """TODO: docs."""
        self.accessed_at = datetime.utcnow()

        if has_been_modified:
            self.modified_at = datetime.utcnow()

        kv_store_info = self.to_key_value_store_info()
        await _update_metadata(data=kv_store_info, entity_directory=self.key_value_store_directory, write_metadata=self.client.write_metadata)


def _find_or_cache_key_value_store_by_possible_id(client: 'MemoryStorage', entry_name_or_id: str) -> Optional['KeyValueStoreClient']:
    # First check memory cache
    found = next((store for store in client.key_value_stores_handled
                  if store.id == entry_name_or_id or (store.name and store.name.lower() == entry_name_or_id.lower())), None)

    if found is not None:
        return found

    key_value_store_dir = os.path.join(client.key_value_stores_directory, entry_name_or_id)
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

            # TODO: Check necessity of final_file_content in Python
            final_file_content = file_content

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
                # final_file_content = file_content
            elif 'application/json' in content_type:
                try:
                    # Try parsing the JSON ahead of time (not ideal but solves invalid files being loaded into stores)
                    json.loads(file_content)
                    # final_file_content = file_content
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
            # elif 'text/plain' in content_type:
            #     final_file_content = file_content

            name_split = entry.name.split('.')

            if file_extension != '':
                name_split.pop()

            key = '.'.join(name_split)

            new_record = {
                'key': key,
                'extension': extension,
                'value': final_file_content,
                'content_type': content_type,
                **internal_records.get(key, {}),
            }

            internal_records[key] = new_record

    if id is None and name is None:
        is_uuid = uuid_regex.match(entry_name_or_id)

        if is_uuid is not None:
            id = entry_name_or_id
        else:
            name = entry_name_or_id

    new_client = KeyValueStoreClient(base_storage_directory=client.key_value_stores_directory, client=client, id=id, name=name)

    # Overwrite properties
    new_client.accessed_at = accessed_at
    new_client.created_at = created_at
    new_client.modified_at = modified_at

    for key, record in internal_records.items():
        # TODO: possibly do a copy/deepcopy of record?
        new_client.key_value_entries[key] = record

    client.key_value_stores_handled.append(new_client)

    return new_client
