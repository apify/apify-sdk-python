
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
    pass
