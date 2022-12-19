import json
import os
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Tuple

import aiofiles
from aiofiles.os import makedirs, remove

from .._utils import _force_remove, json_serializer


class StorageEntityType(Enum):
    DATASET = 1
    KEY_VALUE_STORE = 2
    REQUEST_QUEUE = 3


async def update_metadata(*, data: Dict, entity_directory: str, write_metadata: bool) -> None:
    # Skip writing the actual metadata file. This is done after ensuring the directory exists so we have the directory present
    if not write_metadata:
        return

    # Ensure the directory for the entity exists
    await makedirs(entity_directory, exist_ok=True)

    # Write the metadata to the file
    file_path = os.path.join(entity_directory, '__metadata__.json')
    async with aiofiles.open(file_path, mode='wb') as f:
        # TODO: Check how to dump to JSON properly with aiofiles...
        await f.write(json.dumps(data, ensure_ascii=False, indent=2, default=json_serializer).encode('utf-8'))
        # json.dump(data, f)


async def _check_conditions(entity_directory: str, persist_storage: bool) -> None:
    # Skip writing files to the disk if the client has the option set to false
    if not persist_storage:
        return

    # Ensure the directory for the entity exists
    await makedirs(entity_directory, exist_ok=True)


async def update_dataset_items(
    *,
    data: List[Tuple[str, Dict]],
    entity_directory: str,
    persist_storage: bool,
) -> None:
    await _check_conditions(entity_directory, persist_storage)
    # Save all the new items to the disk
    for idx, item in data:
        file_path = os.path.join(entity_directory, f'{idx}.json')
        async with aiofiles.open(file_path, mode='wb') as f:
            await f.write(json.dumps(item, ensure_ascii=False, indent=2, default=json_serializer).encode('utf-8'))


async def set_or_delete_key_value_store_record(
    *,
    entity_directory: str,
    persist_storage: bool,
    record: Dict,
    should_set: bool,
    write_metadata: bool,
) -> None:
    await _check_conditions(entity_directory, persist_storage)

    # Create files for the record
    record_path = os.path.join(entity_directory, f"""{record['key']}.{record['extension']}""")
    record_metadata_path = os.path.join(entity_directory, f"""{record['key']}.__metadata__.json""")

    await _force_remove(record_path)
    await _force_remove(record_metadata_path)

    if should_set:
        if write_metadata:
            async with aiofiles.open(record_metadata_path, mode='wb') as f:
                await f.write(json.dumps({
                    'key': record['key'],
                    'contentType': record.get('content_type') or 'unknown/no content type',
                    'extension': record['extension'],
                }, ensure_ascii=False, indent=2, default=json_serializer).encode('utf-8'))

        # Convert to bytes if string
        if isinstance(record['value'], str):
            record['value'] = record['value'].encode('utf-8')

        async with aiofiles.open(record_path, mode='wb') as f:
            await f.write(record['value'])


async def update_request_queue_item(
    *,
    request_id: str,
    request: Dict,
    entity_directory: str,
    persist_storage: bool,
) -> None:
    await _check_conditions(entity_directory, persist_storage)

    # Write the request to the file
    file_path = os.path.join(entity_directory, f'{request_id}.json')
    async with aiofiles.open(file_path, mode='wb') as f:
        await f.write(json.dumps(request, ensure_ascii=False, indent=2, default=json_serializer).encode('utf-8'))


async def delete_request(*, request_id: str, entity_directory: str) -> None:
    # Ensure the directory for the entity exists
    await makedirs(entity_directory, exist_ok=True)

    file_path = os.path.join(entity_directory, f'{request_id}.json')
    await _force_remove(file_path)
