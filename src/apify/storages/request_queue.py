from typing import Any, Dict, Optional, TypedDict, TypeVar, Union, overload

from apify_client import ApifyClientAsync
from apify_client.clients import RequestQueueClientAsync

from ..config import Configuration
from ..memory_storage import MemoryStorage
from ..memory_storage.resource_clients import RequestQueueClient
from ._utils import _purge_default_storages

"""
Copy-paste of method interfaces from Crawlee's implementation
constructor(options: RequestQueueOptions, readonly config = Configuration.getGlobalConfig()) {
    this.id = options.id;
    this.name = options.name;
    this.client = options.client.requestQueue(this.id, {
        clientKey: this.clientKey,
        timeoutSecs: this.timeoutSecs,
    }) as RequestQueueClient;
}
inProgressCount()
async addRequest(requestLike: Request | RequestOptions, options: RequestQueueOperationOptions = {}): Promise<QueueOperationInfo>
async addRequests(
    requestsLike: (Request | RequestOptions)[],
    options: RequestQueueOperationOptions = {},
): Promise<BatchAddRequestsResult>
async getRequest<T extends Dictionary = Dictionary>(id: string): Promise<Request<T> | null>
async fetchNextRequest<T extends Dictionary = Dictionary>(): Promise<Request<T> | null>
async markRequestHandled(request: Request): Promise<QueueOperationInfo | null>
async reclaimRequest(request: Request, options: RequestQueueOperationOptions = {}): Promise<QueueOperationInfo | null>
async isEmpty(): Promise<boolean>
async isFinished(): Promise<boolean>
private _reset()
protected _cacheRequest(cacheKey: string, queueOperationInfo: QueueOperationInfo): void
protected async _ensureHeadIsNonEmpty(
    ensureConsistency = false,
    limit = Math.max(this.inProgressCount() * QUERY_HEAD_BUFFER, QUERY_HEAD_MIN_LENGTH),
    iteration = 0,
): Promise<boolean>
private _maybeAddRequestToQueueHead(requestId: string, forefront: boolean): void
async drop(): Promise<void>
async handledCount(): Promise<number>
async getInfo(): Promise<RequestQueueInfo | undefined>
static async open(queueIdOrName?: string | null, options: StorageManagerOptions = {}): Promise<RequestQueue>
"""


class RequestQueue:
    _id: str
    _name: Optional[str]
    _client: Union[RequestQueueClientAsync, RequestQueueClient]

    def __init__(self, id: str, name: Optional[str], client: Union[ApifyClientAsync, MemoryStorage]) -> None:
        """TODO: docs (constructor should be "internal")."""
        self._id = id
        self._name = name
        self._client = client.request_queue(self._id)

    @classmethod
    async def open(cls, store_id_or_name: str, client: Union[ApifyClientAsync, MemoryStorage], config: Configuration) -> 'RequestQueue':
        if config.purge_on_start:
            await _purge_default_storages(client)

        request_queue_client = client.request_queue(store_id_or_name)
        request_queue_info = await request_queue_client.get()
        if not request_queue_info:
            request_queue_info = await client.request_queues().get_or_create(name=store_id_or_name)

        return RequestQueue(request_queue_info['id'], request_queue_info['name'], client)
