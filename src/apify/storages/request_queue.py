from typing import Optional, Union

from apify_client import ApifyClientAsync
from apify_client.clients import RequestQueueClientAsync

from ..config import Configuration
from ..memory_storage import MemoryStorage
from ..memory_storage.resource_clients import RequestQueueClient
from ._utils import _crypto_random_object_id


class RequestQueue:
    """TODO: docs."""

    _id: str
    _name: Optional[str]
    _client: Union[RequestQueueClientAsync, RequestQueueClient]
    _config: Configuration
    _client_key = _crypto_random_object_id()

    def __init__(self, id: str, name: Optional[str], client: Union[ApifyClientAsync, MemoryStorage]) -> None:
        """TODO: docs (constructor should be "internal")."""
        self._id = id
        self._name = name
        self._client = client.request_queue(self._id, client_key=self._client_key)
        self._config = Configuration.get_global_configuration()  # We always use the global config

    @classmethod
    async def _create_instance(cls, request_queue_id_or_name: str, client: Union[ApifyClientAsync, MemoryStorage]) -> 'RequestQueue':
        request_queue_client = client.request_queue(request_queue_id_or_name)
        request_queue_info = await request_queue_client.get()
        if not request_queue_info:
            request_queue_info = await client.request_queues().get_or_create(name=request_queue_id_or_name)

        return RequestQueue(request_queue_info['id'], request_queue_info.get('name'), client)

    @classmethod
    def _get_default_name(cls, config: Configuration) -> str:
        return config.default_request_queue_id
