import json
import os
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional, Union

import aioshutil

from ..._utils import _filter_out_none_values_recursively, _json_dumps
from ..file_storage_utils import _delete_request, _update_metadata, _update_request_queue_item
from ._utils import StorageTypes, _raise_on_duplicate_entry, _raise_on_non_existing, _unique_key_to_request_id, uuid_regex

if TYPE_CHECKING:
    from ..memory_storage import MemoryStorage


class RequestQueueClient:
    """TODO: docs."""

    created_at = datetime.utcnow()
    accessed_at = datetime.utcnow()
    modified_at = datetime.utcnow()
    handled_request_count = 0
    pending_request_count = 0
    requests: Dict[str, Dict] = {}

    def __init__(self, *, base_storage_directory: str, client: 'MemoryStorage', id: Optional[str] = None, name: Optional[str] = None) -> None:
        """TODO: docs."""
        self.id = str(uuid.uuid4()) if id is None else id
        self.request_queue_directory = os.path.join(base_storage_directory, name or self.id)
        self.client = client
        self.name = name

    async def get(self) -> Optional[Dict]:
        """TODO: docs."""
        found = _find_or_cache_request_queue_by_possible_id(self.client, self.name or self.id)

        if found:
            await found.update_timestamps(False)
            return found.to_request_queue_info()

        return None

    async def update(self, *, name: Optional[str] = None) -> Dict:
        """TODO: docs."""
        # Check by id
        existing_store_by_id = _find_or_cache_request_queue_by_possible_id(self.client, self.name or self.id)

        if existing_store_by_id is None:
            _raise_on_non_existing(StorageTypes.REQUEST_QUEUE, self.id)

        # Skip if no changes
        if name is None:
            return existing_store_by_id.to_request_queue_info()

        # Check that name is not in use already
        existing_store_by_name = next(
            (store for store in self.client.request_queues_handled if store.name and store.name.lower() == name.lower()), None)

        if existing_store_by_name is not None:
            _raise_on_duplicate_entry(StorageTypes.REQUEST_QUEUE, 'name', name)

        existing_store_by_id.name = name

        previous_dir = existing_store_by_id.request_queue_directory

        existing_store_by_id.request_queue_directory = os.path.join(self.client.request_queues_directory, name)

        # Remove new directory if it exists
        # TODO: compare to using os.renames, which has problems when target dir exists
        # TODO: check if ignore errors needed...
        await aioshutil.rmtree(existing_store_by_id.request_queue_directory, ignore_errors=True)
        # Copy the previous directory to the new one
        await aioshutil.copytree(previous_dir, existing_store_by_id.request_queue_directory)
        # Remove the previous directory
        await aioshutil.rmtree(previous_dir)

        # Update timestamps
        await existing_store_by_id.update_timestamps(True)

        return existing_store_by_id.to_request_queue_info()

    async def delete(self) -> None:
        """TODO: docs."""
        store = next((store for store in self.client.request_queues_handled if store.id == self.id), None)

        if store is not None:
            self.client.request_queues_handled.remove(store)
            store.pending_request_count = 0
            store.requests.clear()

            await aioshutil.rmtree(store.request_queue_directory)

    async def list_head(self, *, limit: Optional[int] = None) -> Dict:
        """TODO: docs."""
        existing_store_by_id = _find_or_cache_request_queue_by_possible_id(self.client, self.name or self.id)

        if existing_store_by_id is None:
            _raise_on_non_existing(StorageTypes.REQUEST_QUEUE, self.id)

        await existing_store_by_id.update_timestamps(False)

        items: List[Dict] = []

        for request in existing_store_by_id.requests.values():
            if len(items) == limit:
                break

            if request['orderNo']:
                items.append(request)

        return {
            'limit': limit,
            'hadMultipleClients': False,
            'queueModifiedAt': existing_store_by_id.modified_at,
            'items': list(map(lambda item: self._json_to_request(item['json']), items)),
        }

    async def add_request(self, request: Dict, *, forefront: Optional[bool] = None) -> Dict:
        """TODO: docs."""
        existing_store_by_id = _find_or_cache_request_queue_by_possible_id(self.client, self.name or self.id)

        if existing_store_by_id is None:
            _raise_on_non_existing(StorageTypes.REQUEST_QUEUE, self.id)

        request_model = self._create_internal_request(request, forefront)

        existing_request_with_id = existing_store_by_id.requests.get(request_model['id'])

        # We already have the request present, so we return information about it
        if existing_request_with_id is not None:
            await existing_store_by_id.update_timestamps(False)

            return {
                'requestId': existing_request_with_id['id'],
                'wasAlreadyHandled': existing_request_with_id['orderNo'] is None,
                'wasAlreadyPresent': True,
            }

        existing_store_by_id.requests[request_model['id']] = request_model
        existing_store_by_id.pending_request_count += 1 if request_model['orderNo'] is None else 0
        await existing_store_by_id.update_timestamps(True)
        await _update_request_queue_item(
            request=request_model,
            request_id=request_model['id'],
            entity_directory=existing_store_by_id.request_queue_directory,
            persist_storage=self.client.persist_storage,
        )

        return {
            'requestId': request_model['id'],
            # We return wasAlreadyHandled: false even though the request may
            # have been added as handled, because that's how API behaves.
            'wasAlreadyHandled': False,
            'wasAlreadyPresent': False,
        }

    async def get_request(self, request_id: str) -> Optional[Dict]:
        """TODO: docs."""
        existing_store_by_id = _find_or_cache_request_queue_by_possible_id(self.client, self.name or self.id)

        if existing_store_by_id is None:
            _raise_on_non_existing(StorageTypes.REQUEST_QUEUE, self.id)

        await existing_store_by_id.update_timestamps(False)

        request = existing_store_by_id.requests.get(request_id)
        return self._json_to_request(request['json'] if request is not None else None)

    async def update_request(self, request: Dict, *, forefront: Optional[bool] = None) -> Dict:
        """TODO: docs."""
        existing_store_by_id = _find_or_cache_request_queue_by_possible_id(self.client, self.name or self.id)

        if existing_store_by_id is None:
            _raise_on_non_existing(StorageTypes.REQUEST_QUEUE, self.id)

        request_model = self._create_internal_request(request, forefront)

        # First we need to check the existing request to be
        # able to return information about its handled state.

        existing_request = existing_store_by_id.requests.get(request_model['id'])

        # Undefined means that the request is not present in the queue.
        # We need to insert it, to behave the same as API.
        if existing_request is None:
            return await self.add_request(request, forefront=forefront)

        # When updating the request, we need to make sure that
        # the handled counts are updated correctly in all cases.
        existing_store_by_id.requests[request_model['id']] = request_model

        handled_count_adjustment = 0
        is_request_handled_state_changing = type(existing_request['orderNo']) != type(request_model['orderNo'])  # noqa
        request_was_handled_before_update = existing_request['orderNo'] is None

        if is_request_handled_state_changing:
            handled_count_adjustment += 1
        if request_was_handled_before_update:
            handled_count_adjustment = -handled_count_adjustment

        existing_store_by_id.pending_request_count += handled_count_adjustment
        await existing_store_by_id.update_timestamps(True)
        await _update_request_queue_item(
            request=request_model,
            request_id=request_model['id'],
            entity_directory=existing_store_by_id.request_queue_directory,
            persist_storage=self.client.persist_storage,
        )

        return {
            'requestId': request_model['id'],
            'wasAlreadyHandled': request_was_handled_before_update,
            'wasAlreadyPresent': True,
        }

    async def delete_request(self, request_id: str) -> None:
        """TODO: docs."""
        existing_store_by_id = _find_or_cache_request_queue_by_possible_id(self.client, self.name or self.id)

        if existing_store_by_id is None:
            _raise_on_non_existing(StorageTypes.REQUEST_QUEUE, self.id)

        request = existing_store_by_id.requests.get(request_id)

        if request:
            del existing_store_by_id.requests[request_id]
            existing_store_by_id.pending_request_count -= 0 if request['orderNo'] is None else 1
            await existing_store_by_id.update_timestamps(True)
            await _delete_request(entity_directory=existing_store_by_id.request_queue_directory, request_id=request_id)

    def to_request_queue_info(self) -> Dict:
        """TODO: docs."""
        return {
            'accessedAt': self.accessed_at,
            'createdAt': self.created_at,
            'hadMultipleClients': False,
            'handledRequestCount': self.handled_request_count,
            'id': self.id,
            'modifiedAt': self.modified_at,
            'name': self.name,
            'pendingRequestCount': self.pending_request_count,
            'stats': {},
            'totalRequestCount': len(self.requests),
            'userId': '1',
        }

    async def update_timestamps(self, has_been_modified: bool) -> None:
        """TODO: docs."""
        self.accessed_at = datetime.utcnow()

        if has_been_modified:
            self.modified_at = datetime.utcnow()

        request_queue_info = self.to_request_queue_info()
        await _update_metadata(data=request_queue_info, entity_directory=self.request_queue_directory, write_metadata=self.client.write_metadata)

    def _json_to_request(self, request_json: Optional[str]) -> Optional[dict]:
        if request_json is None:
            return None
        request = json.loads(request_json)
        return _filter_out_none_values_recursively(request)

    def _create_internal_request(self, request: Dict, forefront: Optional[bool]) -> Dict:
        order_no = self._calculate_order_no(request, forefront)
        id = _unique_key_to_request_id(request['uniqueKey'])

        if request.get('id') is not None and request['id'] != id:
            raise ValueError('Request ID does not match its unique_key.')

        json_request = _json_dumps({**request, 'id': id})
        return {
            'id': id,
            'json': json_request,
            'method': request.get('method'),
            'orderNo': order_no,
            'retryCount': request.get('retryCount', 0),
            'uniqueKey': request['uniqueKey'],
            'url': request['url'],
        }

    def _calculate_order_no(self, request: Dict, forefront: Optional[bool]) -> Optional[int]:
        if request.get('handledAt') is not None:
            return None

        timestamp = int(round(datetime.utcnow().timestamp()))

        return -timestamp if forefront else timestamp


def _find_or_cache_request_queue_by_possible_id(client: 'MemoryStorage', entry_name_or_id: str) -> Optional['RequestQueueClient']:
    # First check memory cache
    found = next((store for store in client.request_queues_handled
                  if store.id == entry_name_or_id or (store.name and store.name.lower() == entry_name_or_id.lower())), None)

    if found is not None:
        return found

    request_queues_dir = os.path.join(client.request_queues_directory, entry_name_or_id)
    # Check if directory exists
    if not os.access(request_queues_dir, os.F_OK):
        return None

    id: Union[str, None] = None
    name: Union[str, None] = None
    created_at = datetime.utcnow()
    accessed_at = datetime.utcnow()
    modified_at = datetime.utcnow()
    handled_request_count = 0
    pending_request_count = 0
    entries: List[Dict] = []

    # Access the request queue folder
    for entry in os.scandir(request_queues_dir):
        if entry.is_file():
            if entry.name == '__metadata__.json':
                # We have found the store metadata file, build out information based on it
                with open(os.path.join(request_queues_dir, entry.name)) as f:
                    metadata = json.load(f)
                id = metadata['id']
                name = metadata['name']
                created_at = datetime.strptime(metadata['createdAt'], '%Y-%m-%dT%H:%M:%S.%fZ')
                accessed_at = datetime.strptime(metadata['accessedAt'], '%Y-%m-%dT%H:%M:%S.%fZ')
                modified_at = datetime.strptime(metadata['modifiedAt'], '%Y-%m-%dT%H:%M:%S.%fZ')
                handled_request_count = metadata['handledRequestCount']
                pending_request_count = metadata['pendingRequestCount']

                continue

            with open(os.path.join(request_queues_dir, entry.name)) as f:
                request = json.load(f)
            entries.append(request)

    if id is None and name is None:
        is_uuid = uuid_regex.match(entry_name_or_id)

        if is_uuid is not None:
            id = entry_name_or_id
        else:
            name = entry_name_or_id

    new_client = RequestQueueClient(base_storage_directory=client.request_queues_directory, client=client, id=id, name=name)

    # Overwrite properties
    new_client.accessed_at = accessed_at
    new_client.created_at = created_at
    new_client.modified_at = modified_at
    new_client.handled_request_count = handled_request_count
    new_client.pending_request_count = pending_request_count

    for request in entries:
        # TODO: possibly do a copy/deepcopy of request?
        new_client.requests[request['id']] = request

    client.request_queues_handled.append(new_client)

    return new_client
