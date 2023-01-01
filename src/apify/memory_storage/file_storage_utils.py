import os
from typing import Dict, List, Tuple

import aiofiles
from aiofiles.os import makedirs

from .._utils import _force_remove, _json_dumps


async def _update_metadata(*, data: Dict, entity_directory: str, write_metadata: bool) -> None:
    # Skip writing the actual metadata file. This is done after ensuring the directory exists so we have the directory present
    if not write_metadata:
        return

    # Ensure the directory for the entity exists
    await makedirs(entity_directory, exist_ok=True)

    # Write the metadata to the file
    file_path = os.path.join(entity_directory, '__metadata__.json')
    async with aiofiles.open(file_path, mode='wb') as f:
        await f.write(_json_dumps(data).encode('utf-8'))


async def _update_dataset_items(
    *,
    data: List[Tuple[str, Dict]],
    entity_directory: str,
    persist_storage: bool,
) -> None:
    # Skip writing files to the disk if the client has the option set to false
    if not persist_storage:
        return

    # Ensure the directory for the entity exists
    await makedirs(entity_directory, exist_ok=True)

    # Save all the new items to the disk
    for idx, item in data:
        file_path = os.path.join(entity_directory, f'{idx}.json')
        async with aiofiles.open(file_path, mode='wb') as f:
            await f.write(_json_dumps(item).encode('utf-8'))


async def _set_or_delete_key_value_store_record(
    *,
    entity_directory: str,
    persist_storage: bool,
    record: Dict,
    should_set: bool,
    write_metadata: bool,
) -> None:
    # Skip writing files to the disk if the client has the option set to false
    if not persist_storage:
        return

    # Ensure the directory for the entity exists
    await makedirs(entity_directory, exist_ok=True)

    # Create files for the record
    record_path = os.path.join(entity_directory, f"""{record['key']}.{record['extension']}""")
    record_metadata_path = os.path.join(entity_directory, f"""{record['key']}.__metadata__.json""")

    await _force_remove(record_path)
    await _force_remove(record_metadata_path)

    if should_set:
        if write_metadata:
            async with aiofiles.open(record_metadata_path, mode='wb') as f:
                await f.write(_json_dumps({
                    'key': record['key'],
                    'contentType': record.get('content_type') or 'unknown/no content type',
                    'extension': record['extension'],
                }).encode('utf-8'))

        # Convert to bytes if string
        if isinstance(record['value'], str):
            record['value'] = record['value'].encode('utf-8')

        async with aiofiles.open(record_path, mode='wb') as f:
            await f.write(record['value'])


async def _update_request_queue_item(
    *,
    request_id: str,
    request: Dict,
    entity_directory: str,
    persist_storage: bool,
) -> None:
    # Skip writing files to the disk if the client has the option set to false
    if not persist_storage:
        return

    # Ensure the directory for the entity exists
    await makedirs(entity_directory, exist_ok=True)

    # Write the request to the file
    file_path = os.path.join(entity_directory, f'{request_id}.json')
    async with aiofiles.open(file_path, mode='wb') as f:
        await f.write(_json_dumps(request).encode('utf-8'))


async def _delete_request(*, request_id: str, entity_directory: str) -> None:
    # Ensure the directory for the entity exists
    await makedirs(entity_directory, exist_ok=True)

    file_path = os.path.join(entity_directory, f'{request_id}.json')
    await _force_remove(file_path)
