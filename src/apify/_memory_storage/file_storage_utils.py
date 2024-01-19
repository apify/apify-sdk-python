from __future__ import annotations

import os

import aiofiles
from aiofiles.os import makedirs
from apify_shared.utils import json_dumps

from apify._utils import force_remove


async def update_metadata(*, data: dict, entity_directory: str, write_metadata: bool) -> None:
    # Skip writing the actual metadata file. This is done after ensuring the directory exists so we have the directory present
    if not write_metadata:
        return

    # Ensure the directory for the entity exists
    await makedirs(entity_directory, exist_ok=True)

    # Write the metadata to the file
    file_path = os.path.join(entity_directory, '__metadata__.json')
    async with aiofiles.open(file_path, mode='wb') as f:
        await f.write(json_dumps(data).encode('utf-8'))


async def _update_dataset_items(
    *,
    data: list[tuple[str, dict]],
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
            await f.write(json_dumps(item).encode('utf-8'))


async def update_request_queue_item(
    *,
    request_id: str,
    request: dict,
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
        await f.write(json_dumps(request).encode('utf-8'))


async def delete_request(*, request_id: str, entity_directory: str) -> None:
    # Ensure the directory for the entity exists
    await makedirs(entity_directory, exist_ok=True)

    file_path = os.path.join(entity_directory, f'{request_id}.json')
    await force_remove(file_path)
