import asyncio
from collections import (
    OrderedDict,  # TODO: This vs from typing import OrderedDict... https://stackoverflow.com/questions/41207128/how-do-i-specify-ordereddict-k-v-types-for-mypy-type-annotation
)
from datetime import datetime
from typing import Any, Coroutine, Dict, Optional, Set, TypedDict, TypeVar, Union, overload

from apify_client import ApifyClientAsync
from apify_client.clients import RequestQueueClientAsync

from .._utils import _unique_key_to_request_id
from ..config import Configuration
from ..consts import REQUEST_QUEUE_HEAD_MAX_LIMIT
from ..memory_storage import MemoryStorage
from ..memory_storage.resource_clients import RequestQueueClient
from ._utils import LRUCache, _crypto_random_object_id
from .storage_manager import StorageManager

MAX_CACHED_REQUESTS = 1_000_000

QUERY_HEAD_MIN_LENGTH = 100
"""When requesting queue head we always fetch requestsInProgressCount * QUERY_HEAD_BUFFER number of requests."""

QUERY_HEAD_BUFFER = 3

API_PROCESSED_REQUESTS_DELAY_MILLIS = 10_000
"""
 If queue was modified (request added/updated/deleted) before more than API_PROCESSED_REQUESTS_DELAY_MILLIS
 then we assume the get head operation to be consistent.
"""

MAX_QUERIES_FOR_CONSISTENCY = 6
"""
 How many times we try to get queue head with queueModifiedAt older than API_PROCESSED_REQUESTS_DELAY_MILLIS.
"""

RECENTLY_HANDLED_CACHE_SIZE = 1000
"""
 This number must be large enough so that processing of all these requests cannot be done in
 a time lower than expected maximum latency of DynamoDB, but low enough not to waste too much memory.
"""

STORAGE_CONSISTENCY_DELAY_MILLIS = 3000
"""
 Indicates how long it usually takes for the underlying storage to propagate all writes
 to be available to subsequent reads.
"""

"""
Copy-paste of method interfaces from Crawlee's implementation
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
"""


class RequestQueue:
    _id: str
    _name: Optional[str]
    _client: Union[RequestQueueClientAsync, RequestQueueClient]
    _config: Configuration
    _client_key = _crypto_random_object_id()
    _queue_head_dict: OrderedDict[str, str]
    _query_queue_head_promise: Optional[Coroutine]
    _in_progress: Set[str]
    _last_activity: datetime
    _internal_timeout_millis = 5 * 60e3
    _recently_handled: LRUCache[bool]
    _assumed_total_count = 0
    _assumed_handled_count = 0
    _requests_cache: LRUCache

    def __init__(self, id: str, name: Optional[str], client: Union[ApifyClientAsync, MemoryStorage]) -> None:
        """TODO: docs (constructor should be "internal")."""
        self._id = id
        self._name = name
        self._client = client.request_queue(self._id, client_key=self._client_key)
        self._config = Configuration.get_global_configuration()  # We always use the global config
        self._queue_head_dict = OrderedDict()
        self._query_queue_head_promise = None
        self._in_progress = set()
        self._last_activity = datetime.utcnow()
        self._recently_handled = LRUCache[bool](max_length=RECENTLY_HANDLED_CACHE_SIZE)
        self._requests_cache = LRUCache(max_length=MAX_CACHED_REQUESTS)

    @classmethod
    async def _create_instance(cls, request_queue_id_or_name: str, client: Union[ApifyClientAsync, MemoryStorage]) -> 'RequestQueue':
        request_queue_client = client.request_queue(request_queue_id_or_name)
        request_queue_info = await request_queue_client.get()
        if not request_queue_info:
            request_queue_info = await client.request_queues().get_or_create(name=request_queue_id_or_name)

        return RequestQueue(request_queue_info['id'], request_queue_info['name'], client)

    @classmethod
    def _get_default_name(cls, config: Configuration) -> str:
        return config.default_request_queue_id

    async def add_request(request_like: Dict, forefront: bool = False) -> Dict:
        pass
    # async addRequest(requestLike: Request | RequestOptions, options: RequestQueueOperationOptions = {}): Promise<QueueOperationInfo> {
    #     ow(requestLike, ow.object.partialShape({
    #         url: ow.string,
    #         id: ow.undefined,
    #     }));
    #     ow(options, ow.object.exactShape({
    #         forefront: ow.optional.boolean,
    #     }));

    #     this.lastActivity = new Date();
    #     const { forefront = false } = options;

    #     const request = requestLike instanceof Request
    #         ? requestLike
    #         : new Request(requestLike);

    #     const cacheKey = getRequestId(request.uniqueKey);
    #     const cachedInfo = this.requestsCache.get(cacheKey);

    #     if (cachedInfo) {
    #         request.id = cachedInfo.id;
    #         return {
    #             wasAlreadyPresent: true,
    #             // We may assume that if request is in local cache then also the information if the
    #             // request was already handled is there because just one client should be using one queue.
    #             wasAlreadyHandled: cachedInfo.isHandled,
    #             requestId: cachedInfo.id,
    #             uniqueKey: cachedInfo.uniqueKey,
    #         };
    #     }

    #     const queueOperationInfo = await this.client.addRequest(request, { forefront }) as QueueOperationInfo;
    #     queueOperationInfo.uniqueKey = request.uniqueKey;

    #     const { requestId, wasAlreadyPresent } = queueOperationInfo;
    #     this._cacheRequest(cacheKey, queueOperationInfo);

    #     if (!wasAlreadyPresent && !this.inProgress.has(requestId) && !this.recentlyHandled.get(requestId)) {
    #         this.assumedTotalCount++;

    #         // Performance optimization: add request straight to head if possible
    #         this._maybeAddRequestToQueueHead(requestId, forefront);
    #     }

    #     return queueOperationInfo;
    # }

    async def get_request(self, request_id: str) -> Optional[Dict]:
        return await self._client.get_request(request_id)  # TODO: Maybe create a Request class?
    # async getRequest<T extends Dictionary = Dictionary>(id: string): Promise<Request<T> | null> {
    #     ow(id, ow.string);

    #     const requestOptions = await this.client.getRequest(id);
    #     if (!requestOptions) return null;

    #     return new Request(requestOptions as unknown as RequestOptions);
    # }

    async def fetch_next_request(self) -> Optional[Dict]:
        pass
    # async fetchNextRequest<T extends Dictionary = Dictionary>(): Promise<Request<T> | null> {
    #     await this._ensureHeadIsNonEmpty();

    #     const nextRequestId = this.queueHeadDict.removeFirst();

    #     // We are likely done at this point.
    #     if (!nextRequestId) return null;

    #     // This should never happen, but...
    #     if (this.inProgress.has(nextRequestId) || this.recentlyHandled.get(nextRequestId)) {
    #         this.log.warning('Queue head returned a request that is already in progress?!', {
    #             nextRequestId,
    #             inProgress: this.inProgress.has(nextRequestId),
    #             recentlyHandled: !!this.recentlyHandled.get(nextRequestId),
    #         });
    #         return null;
    #     }

    #     this.inProgress.add(nextRequestId);
    #     this.lastActivity = new Date();

    #     let request;
    #     try {
    #         request = await this.getRequest(nextRequestId);
    #     } catch (e) {
    #         // On error, remove the request from in progress, otherwise it would be there forever
    #         this.inProgress.delete(nextRequestId);
    #         throw e;
    #     }

    #     // NOTE: It can happen that the queue head index is inconsistent with the main queue table. This can occur in two situations:

    #     // 1) Queue head index is ahead of the main table and the request is not present in the main table yet (i.e. getRequest() returned null).
    #     //    In this case, keep the request marked as in progress for a short while,
    #     //    so that isFinished() doesn't return true and _ensureHeadIsNonEmpty() doesn't not load the request
    #     //    into the queueHeadDict straight again. After the interval expires, fetchNextRequest()
    #     //    will try to fetch this request again, until it eventually appears in the main table.
    #     if (!request) {
    #         this.log.debug('Cannot find a request from the beginning of queue, will be retried later', { nextRequestId });
    #         setTimeout(() => {
    #             this.inProgress.delete(nextRequestId);
    #         }, STORAGE_CONSISTENCY_DELAY_MILLIS);
    #         return null;
    #     }

    #     // 2) Queue head index is behind the main table and the underlying request was already handled
    #     //    (by some other client, since we keep the track of handled requests in recentlyHandled dictionary).
    #     //    We just add the request to the recentlyHandled dictionary so that next call to _ensureHeadIsNonEmpty()
    #     //    will not put the request again to queueHeadDict.
    #     if (request.handledAt) {
    #         this.log.debug('Request fetched from the beginning of queue was already handled', { nextRequestId });
    #         this.recentlyHandled.add(nextRequestId, true);
    #         return null;
    #     }

    #     return request;
    # }

    async def mark_request_as_handled(self, request: Dict) -> Optional[Dict]:
        pass
    # async markRequestHandled(request: Request): Promise<QueueOperationInfo | null> {
    #     this.lastActivity = new Date();
    #     ow(request, ow.object.partialShape({
    #         id: ow.string,
    #         uniqueKey: ow.string,
    #         handledAt: ow.optional.string,
    #     }));

    #     if (!this.inProgress.has(request.id)) {
    #         this.log.debug(`Cannot mark request ${request.id} as handled, because it is not in progress!`, { requestId: request.id });
    #         return null;
    #     }

    #     const handledAt = request.handledAt ?? new Date().toISOString();
    #     const queueOperationInfo = await this.client.updateRequest({ ...request, handledAt }) as QueueOperationInfo;
    #     request.handledAt = handledAt;
    #     queueOperationInfo.uniqueKey = request.uniqueKey;

    #     this.inProgress.delete(request.id);
    #     this.recentlyHandled.add(request.id, true);

    #     if (!queueOperationInfo.wasAlreadyHandled) {
    #         this.assumedHandledCount++;
    #     }

    #     this._cacheRequest(getRequestId(request.uniqueKey), queueOperationInfo);

    #     return queueOperationInfo;
    # }

    async def reclaim_request(self, request: Dict, forefront: bool = False) -> Optional[Dict]:
        pass
    # async reclaimRequest(request: Request, options: RequestQueueOperationOptions = {}): Promise<QueueOperationInfo | null> {
    #     this.lastActivity = new Date();
    #     ow(request, ow.object.partialShape({
    #         id: ow.string,
    #         uniqueKey: ow.string,
    #     }));
    #     ow(options, ow.object.exactShape({
    #         forefront: ow.optional.boolean,
    #     }));

    #     const { forefront = false } = options;

    #     if (!this.inProgress.has(request.id)) {
    #         this.log.debug(`Cannot reclaim request ${request.id}, because it is not in progress!`, { requestId: request.id });
    #         return null;
    #     }

    #     // TODO: If request hasn't been changed since the last getRequest(),
    #     //   we don't need to call updateRequest() and thus improve performance.
    #     const queueOperationInfo = await this.client.updateRequest(request, { forefront }) as QueueOperationInfo;
    #     queueOperationInfo.uniqueKey = request.uniqueKey;
    #     this._cacheRequest(getRequestId(request.uniqueKey), queueOperationInfo);

    #     // Wait a little to increase a chance that the next call to fetchNextRequest() will return the request with updated data.
    #     // This is to compensate for the limitation of DynamoDB, where writes might not be immediately visible to subsequent reads.
    #     setTimeout(() => {
    #         if (!this.inProgress.has(request.id)) {
    #             this.log.debug('The request is no longer marked as in progress in the queue?!', { requestId: request.id });
    #             return;
    #         }

    #         this.inProgress.delete(request.id);

    #         // Performance optimization: add request straight to head if possible
    #         this._maybeAddRequestToQueueHead(request.id, forefront);
    #     }, STORAGE_CONSISTENCY_DELAY_MILLIS);

    #     return queueOperationInfo;
    # }

    def _in_progress_count(self) -> int:
        return len(self._in_progress)

    async def is_empty(self) -> bool:
        await self._ensure_head_is_non_empty()
        return len(self._queue_head_dict) == 0

    async def is_finished(self) -> bool:
        if self._in_progress_count() > 0 and (datetime.utcnow() - self._last_activity) > self._internal_timeout_millis:
            message = f'The request queue seems to be stuck for {self._internal_timeout_millis / 1e3}s, resetting internal state.'
            # this.log.warning(message, { inProgress: [...this.inProgress] });
            print('TODO', message)
            self._reset()

        if (len(self._queue_head_dict) > 0 or self._in_progress_count() > 0):
            return False

        is_head_consistent = await self._ensure_head_is_non_empty(True)
        return is_head_consistent and len(self._queue_head_dict) == 0 and self._in_progress_count() == 0

    def _reset(self) -> None:
        self._queue_head_dict.clear()
        self._query_queue_head_promise = None
        self._in_progress.clear()
        self._recently_handled.clear()
        self._assumed_total_count = 0
        self._assumed_handled_count = 0
        self._requests_cache.clear()
        self._last_activity = datetime.utcnow()

    def _cache_request(self, cache_key: str, queue_operation_info: Dict) -> None:
        self._requests_cache.add(cache_key, {
            'id': queue_operation_info['requestId'],
            'isHandled': queue_operation_info['wasAlreadyHandled'],
            'uniqueKey': queue_operation_info['uniqueKey'],
            'wasAlreadyHandled': queue_operation_info['wasAlreadyHandled'],
        })

    async def _queue_query_head(self, limit: int) -> Dict:
        query_started_at = datetime.utcnow()

        list_head = await self._client.list_head(limit=limit)
        for request in list_head['items']:
            # Queue head index might be behind the main table, so ensure we don't recycle requests
            if not request['id'] or not request['uniqueKey'] or request['id'] in self._in_progress or self._recently_handled.get(request['id']):
                continue
            self._queue_head_dict[request['id']] = request['id']
            self._cache_request(_unique_key_to_request_id(request['uniqueKey']), {
                'requestId': request['id'],
                'wasAlreadyHandled': False,
                'wasAlreadyPresent': True,
                'uniqueKey': request['uniqueKey'],
            })

        # This is needed so that the next call to _ensureHeadIsNonEmpty() will fetch the queue head again.
        self._query_queue_head_promise = None

        return {
            'wasLimitReached': len(list_head['items']) >= limit,
            'prevLimit': limit,
            'queueModifiedAt': datetime(list_head['queueModifiedAt']),  # TODO: AAA
            'queryStartedAt': query_started_at,
            'hadMultipleClients': list_head['hadMultipleClients'],
        }

    async def _ensure_head_is_non_empty(self, ensureConsistency: bool = False, limit: Optional[int] = None, iteration: int = 0) -> bool:
        # If is nonempty resolve immediately.
        if len(self._queue_head_dict) > 0:
            return True

        if limit is None:
            limit = max(self._in_progress_count() * QUERY_HEAD_BUFFER, QUERY_HEAD_MIN_LENGTH)

        if self._query_queue_head_promise is None:
            self._query_queue_head_promise = self._queue_query_head(limit)

        queue_head = await self._query_queue_head_promise

        # TODO: I feel this code below can be greatly simplified... (comes from TS implementation *wink*)

        """ If queue is still empty then one of the following holds:
        - the other calls waiting for this promise already consumed all the returned requests
        - the limit was too low and contained only requests in progress
        - the writes from other clients were not propagated yet
        - the whole queue was processed and we are done
        """

        # If limit was not reached in the call then there are no more requests to be returned.
        if (queue_head['prevLimit'] >= REQUEST_QUEUE_HEAD_MAX_LIMIT):
            # this.log.warning(`Reached the maximum number of requests in progress: ${REQUEST_QUEUE_HEAD_MAX_LIMIT}.`);
            print('TODO')

        should_repeat_with_higher_limit = len(
            self._queue_head_dict) == 0 and queue_head['wasLimitReached'] and queue_head['prevLimit'] < REQUEST_QUEUE_HEAD_MAX_LIMIT

        # If ensureConsistency=true then we must ensure that either:
        # - queueModifiedAt is older than queryStartedAt by at least API_PROCESSED_REQUESTS_DELAY_MILLIS
        # - hadMultipleClients=false and this.assumedTotalCount<=this.assumedHandledCount
        is_database_consistent = +queue_head['queryStartedAt'] - +queue_head['queueModifiedAt'] >= API_PROCESSED_REQUESTS_DELAY_MILLIS
        is_locally_consistent = not queue_head['hadMultipleClients'] and self._assumed_total_count <= self._assumed_handled_count
        # Consistent information from one source is enough to consider request queue finished.
        should_repeat_for_consistency = ensureConsistency and not is_database_consistent and not is_locally_consistent

        # If both are false then head is consistent and we may exit.
        if not should_repeat_with_higher_limit and not should_repeat_for_consistency:
            return True

        # If we are querying for consistency then we limit the number of queries to MAX_QUERIES_FOR_CONSISTENCY.
        # If this is reached then we return false so that empty() and finished() returns possibly false negative.
        if not should_repeat_with_higher_limit and iteration > MAX_QUERIES_FOR_CONSISTENCY:
            return False

        next_limit = round(queue_head['prevLimit'] * 1.5) if should_repeat_with_higher_limit else queue_head['prevLimit']

        # If we are repeating for consistency then wait required time.
        if should_repeat_for_consistency:
            delay_millis = API_PROCESSED_REQUESTS_DELAY_MILLIS - (datetime.utcnow() - +queue_head['queueModifiedAt'])
            # this.log.info(`Waiting for ${delayMillis}ms before considering the queue as finished to ensure that the data is consistent.`);
            print('TODO')
            await asyncio.sleep(delay_millis // 1000)

        return await self._ensure_head_is_non_empty(ensureConsistency, next_limit, iteration + 1)

    def _maybe_add_request_to_queue_head(self, request_id: str, forefront: bool) -> None:
        if forefront:
            self._queue_head_dict[request_id] = request_id
            # Move to start, i.e. forefront of the queue
            self._queue_head_dict.move_to_end(request_id, last=False)
        elif self._assumed_total_count < QUERY_HEAD_MIN_LENGTH:
            # OrderedDict puts the item to the end of the queue by default
            self._queue_head_dict[request_id] = request_id

    async def drop(self) -> None:
        """TODO: docs."""
        await self._client.delete()
        await StorageManager.close_storage(self.__class__, self._id, self._name)

    async def get_info(self) -> Optional[Dict]:
        return await self._client.get()

    async def handled_count(self) -> int:
        # NOTE: We keep this function for compatibility with RequestList.handledCount()
        rq_info = await self.get_info()
        # TODO: int() wrapping to trick mypy is hacky, use typed dict?
        return int(rq_info['handledRequestCount']) if rq_info is not None else 0
