import json
import os
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, List, Optional, Union

import aioshutil

from ..._utils import (
    _filter_out_none_values_recursively,
    _force_rename,
    _is_uuid,
    _json_dumps,
    _raise_on_duplicate_storage,
    _raise_on_non_existing_storage,
    _unique_key_to_request_id,
)
from ...consts import StorageTypes
from ..file_storage_utils import _delete_request, _update_metadata, _update_request_queue_item

if TYPE_CHECKING:
    from ..memory_storage import MemoryStorage


class RequestQueueClient:
    """Sub-client for manipulating a single request queue."""

    _id: str
    _request_queue_directory: str
    _client: 'MemoryStorage'
    _name: Optional[str]
    _requests: Dict[str, Dict]
    _created_at: datetime
    _accessed_at: datetime
    _modified_at: datetime
    _handled_request_count = 0  # TODO: Does not seem to be implemented in crawelee, always 0
    _pending_request_count = 0

    def __init__(self, *, base_storage_directory: str, client: 'MemoryStorage', id: Optional[str] = None, name: Optional[str] = None) -> None:
        """Initialize the RequestQueueClient."""
        self._id = str(uuid.uuid4()) if id is None else id
        self._request_queue_directory = os.path.join(base_storage_directory, name or self._id)
        self._client = client
        self._name = name
        self._requests = {}
        self._created_at = datetime.now(timezone.utc)
        self._accessed_at = datetime.now(timezone.utc)
        self._modified_at = datetime.now(timezone.utc)

    async def get(self) -> Optional[Dict]:
        """Retrieve the request queue.

        Returns:
            dict, optional: The retrieved request queue, or None, if it does not exist
        """
        found = _find_or_cache_request_queue_by_possible_id(self._client, self._name or self._id)

        if found:
            await found._update_timestamps(False)
            return found.to_request_queue_info()

        return None

    async def update(self, *, name: Optional[str] = None) -> Dict:
        """Update the request queue with specified fields.

        Args:
            name (str, optional): The new name for the request queue

        Returns:
            dict: The updated request queue
        """
        # Check by id
        existing_queue_by_id = _find_or_cache_request_queue_by_possible_id(self._client, self._name or self._id)

        if existing_queue_by_id is None:
            _raise_on_non_existing_storage(StorageTypes.REQUEST_QUEUE, self._id)

        # Skip if no changes
        if name is None:
            return existing_queue_by_id.to_request_queue_info()

        # Check that name is not in use already
        existing_queue_by_name = next(
            (queue for queue in self._client._request_queues_handled if queue._name and queue._name.lower() == name.lower()), None)

        if existing_queue_by_name is not None:
            _raise_on_duplicate_storage(StorageTypes.REQUEST_QUEUE, 'name', name)

        existing_queue_by_id._name = name

        previous_dir = existing_queue_by_id._request_queue_directory

        existing_queue_by_id._request_queue_directory = os.path.join(self._client._request_queues_directory, name)

        await _force_rename(previous_dir, existing_queue_by_id._request_queue_directory)

        # Update timestamps
        await existing_queue_by_id._update_timestamps(True)

        return existing_queue_by_id.to_request_queue_info()

    async def delete(self) -> None:
        """Delete the request queue."""
        queue = next((queue for queue in self._client._request_queues_handled if queue._id == self._id), None)

        if queue is not None:
            self._client._request_queues_handled.remove(queue)
            queue._pending_request_count = 0
            queue._requests.clear()

            if os.path.exists(queue._request_queue_directory):
                await aioshutil.rmtree(queue._request_queue_directory)

    async def list_head(self, *, limit: Optional[int] = None) -> Dict:
        """Retrieve a given number of requests from the beginning of the queue.

        Args:
            limit (int, optional): How many requests to retrieve

        Returns:
            dict: The desired number of requests from the beginning of the queue.
        """
        existing_queue_by_id = _find_or_cache_request_queue_by_possible_id(self._client, self._name or self._id)

        if existing_queue_by_id is None:
            _raise_on_non_existing_storage(StorageTypes.REQUEST_QUEUE, self._id)

        await existing_queue_by_id._update_timestamps(False)

        items: List[Dict] = []

        for request in existing_queue_by_id._requests.values():
            if len(items) == limit:
                break

            if request['orderNo']:
                items.append(request)

        return {
            'limit': limit,
            'hadMultipleClients': False,
            'queueModifiedAt': existing_queue_by_id._modified_at,
            'items': list(map(lambda item: self._json_to_request(item['json']), items)),
        }

    async def add_request(self, request: Dict, *, forefront: Optional[bool] = None) -> Dict:
        """Add a request to the queue.

        Args:
            request (dict): The request to add to the queue
            forefront (bool, optional): Whether to add the request to the head or the end of the queue

        Returns:
            dict: The added request.
        """
        existing_queue_by_id = _find_or_cache_request_queue_by_possible_id(self._client, self._name or self._id)

        if existing_queue_by_id is None:
            _raise_on_non_existing_storage(StorageTypes.REQUEST_QUEUE, self._id)

        request_model = self._create_internal_request(request, forefront)

        existing_request_with_id = existing_queue_by_id._requests.get(request_model['id'])

        # We already have the request present, so we return information about it
        if existing_request_with_id is not None:
            await existing_queue_by_id._update_timestamps(False)

            return {
                'requestId': existing_request_with_id['id'],
                'wasAlreadyHandled': existing_request_with_id['orderNo'] is None,
                'wasAlreadyPresent': True,
            }

        existing_queue_by_id._requests[request_model['id']] = request_model
        existing_queue_by_id._pending_request_count += 0 if request_model['orderNo'] is None else 1
        await existing_queue_by_id._update_timestamps(True)
        await _update_request_queue_item(
            request=request_model,
            request_id=request_model['id'],
            entity_directory=existing_queue_by_id._request_queue_directory,
            persist_storage=self._client._persist_storage,
        )

        return {
            'requestId': request_model['id'],
            # We return wasAlreadyHandled: false even though the request may
            # have been added as handled, because that's how API behaves.
            'wasAlreadyHandled': False,
            'wasAlreadyPresent': False,
        }

    async def get_request(self, request_id: str) -> Optional[Dict]:
        """Retrieve a request from the queue.

        Args:
            request_id (str): ID of the request to retrieve

        Returns:
            dict, optional: The retrieved request, or None, if it did not exist.
        """
        existing_queue_by_id = _find_or_cache_request_queue_by_possible_id(self._client, self._name or self._id)

        if existing_queue_by_id is None:
            _raise_on_non_existing_storage(StorageTypes.REQUEST_QUEUE, self._id)

        await existing_queue_by_id._update_timestamps(False)

        request = existing_queue_by_id._requests.get(request_id)
        return self._json_to_request(request['json'] if request is not None else None)

    async def update_request(self, request: Dict, *, forefront: Optional[bool] = None) -> Dict:
        """Update a request in the queue.

        Args:
            request (dict): The updated request
            forefront (bool, optional): Whether to put the updated request in the beginning or the end of the queue

        Returns:
            dict: The updated request
        """
        existing_queue_by_id = _find_or_cache_request_queue_by_possible_id(self._client, self._name or self._id)

        if existing_queue_by_id is None:
            _raise_on_non_existing_storage(StorageTypes.REQUEST_QUEUE, self._id)

        request_model = self._create_internal_request(request, forefront)

        # First we need to check the existing request to be
        # able to return information about its handled state.

        existing_request = existing_queue_by_id._requests.get(request_model['id'])

        # Undefined means that the request is not present in the queue.
        # We need to insert it, to behave the same as API.
        if existing_request is None:
            return await self.add_request(request, forefront=forefront)

        # When updating the request, we need to make sure that
        # the handled counts are updated correctly in all cases.
        existing_queue_by_id._requests[request_model['id']] = request_model

        pending_count_adjustment = 0
        is_request_handled_state_changing = type(existing_request['orderNo']) != type(request_model['orderNo'])  # noqa
        request_was_handled_before_update = existing_request['orderNo'] is None

        # We add 1 pending request if previous state was handled
        if is_request_handled_state_changing:
            pending_count_adjustment = 1 if request_was_handled_before_update else -1

        existing_queue_by_id._pending_request_count += pending_count_adjustment
        await existing_queue_by_id._update_timestamps(True)
        await _update_request_queue_item(
            request=request_model,
            request_id=request_model['id'],
            entity_directory=existing_queue_by_id._request_queue_directory,
            persist_storage=self._client._persist_storage,
        )

        return {
            'requestId': request_model['id'],
            'wasAlreadyHandled': request_was_handled_before_update,
            'wasAlreadyPresent': True,
        }

    async def delete_request(self, request_id: str) -> None:
        """Delete a request from the queue.

        Args:
            request_id (str): ID of the request to delete.
        """
        existing_queue_by_id = _find_or_cache_request_queue_by_possible_id(self._client, self._name or self._id)

        if existing_queue_by_id is None:
            _raise_on_non_existing_storage(StorageTypes.REQUEST_QUEUE, self._id)

        request = existing_queue_by_id._requests.get(request_id)

        if request:
            del existing_queue_by_id._requests[request_id]
            existing_queue_by_id._pending_request_count -= 0 if request['orderNo'] is None else 1
            await existing_queue_by_id._update_timestamps(True)
            await _delete_request(entity_directory=existing_queue_by_id._request_queue_directory, request_id=request_id)

    def to_request_queue_info(self) -> Dict:
        """Retrieve the request queue store info."""
        return {
            'accessedAt': self._accessed_at,
            'createdAt': self._created_at,
            'hadMultipleClients': False,
            'handledRequestCount': self._handled_request_count,
            'id': self._id,
            'modifiedAt': self._modified_at,
            'name': self._name,
            'pendingRequestCount': self._pending_request_count,
            'stats': {},
            'totalRequestCount': len(self._requests),
            'userId': '1',
        }

    async def _update_timestamps(self, has_been_modified: bool) -> None:
        self._accessed_at = datetime.now(timezone.utc)

        if has_been_modified:
            self._modified_at = datetime.now(timezone.utc)

        request_queue_info = self.to_request_queue_info()
        await _update_metadata(data=request_queue_info, entity_directory=self._request_queue_directory, write_metadata=self._client._write_metadata)

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

        timestamp = int(round(datetime.now(timezone.utc).timestamp()))

        return -timestamp if forefront else timestamp


def _find_or_cache_request_queue_by_possible_id(client: 'MemoryStorage', entry_name_or_id: str) -> Optional['RequestQueueClient']:
    # First check memory cache
    found = next((queue for queue in client._request_queues_handled
                  if queue._id == entry_name_or_id or (queue._name and queue._name.lower() == entry_name_or_id.lower())), None)

    if found is not None:
        return found

    request_queues_dir = os.path.join(client._request_queues_directory, entry_name_or_id)
    # Check if directory exists
    if not os.access(request_queues_dir, os.F_OK):
        return None

    id: Union[str, None] = None
    name: Union[str, None] = None
    created_at = datetime.now(timezone.utc)
    accessed_at = datetime.now(timezone.utc)
    modified_at = datetime.now(timezone.utc)
    handled_request_count = 0
    pending_request_count = 0
    entries: List[Dict] = []

    # Access the request queue folder
    for entry in os.scandir(request_queues_dir):
        if entry.is_file():
            if entry.name == '__metadata__.json':
                # We have found the queue's metadata file, build out information based on it
                with open(os.path.join(request_queues_dir, entry.name)) as f:
                    metadata = json.load(f)
                id = metadata['id']
                name = metadata['name']
                created_at = datetime.fromisoformat(metadata['createdAt'])
                accessed_at = datetime.fromisoformat(metadata['accessedAt'])
                modified_at = datetime.fromisoformat(metadata['modifiedAt'])
                handled_request_count = metadata['handledRequestCount']
                pending_request_count = metadata['pendingRequestCount']

                continue

            with open(os.path.join(request_queues_dir, entry.name)) as f:
                request = json.load(f)
            entries.append(request)

    if id is None and name is None:
        is_uuid = _is_uuid(entry_name_or_id)

        if is_uuid:
            id = entry_name_or_id
        else:
            name = entry_name_or_id

    new_client = RequestQueueClient(base_storage_directory=client._request_queues_directory, client=client, id=id, name=name)

    # Overwrite properties
    new_client._accessed_at = accessed_at
    new_client._created_at = created_at
    new_client._modified_at = modified_at
    new_client._handled_request_count = handled_request_count
    new_client._pending_request_count = pending_request_count

    for request in entries:
        new_client._requests[request['id']] = request

    client._request_queues_handled.append(new_client)

    return new_client
