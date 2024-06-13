from __future__ import annotations

from typing import TYPE_CHECKING

from crawlee.base_storage_client.base_request_queue_client import BaseRequestQueueClient
from crawlee.models import Request, RequestQueueHead, RequestQueueMetadata, RequestQueueOperationInfo
from typing_extensions import override

if TYPE_CHECKING:
    from apify_client.clients import RequestQueueClientAsync


class RequestQueueClient(BaseRequestQueueClient):
    """Request queue resource client implementation based on the Apify platform storage."""

    def __init__(self, apify_request_queue_client: RequestQueueClientAsync) -> None:
        self._client = apify_request_queue_client

    @override
    async def get(self) -> RequestQueueMetadata | None:
        result = await self._client.get()
        return RequestQueueMetadata.model_validate(result) if result else None

    @override
    async def update(
        self,
        *,
        name: str | None = None,
    ) -> RequestQueueMetadata:
        return RequestQueueMetadata.model_validate(
            await self._client.update(
                name=name,
            )
        )

    @override
    async def delete(self) -> None:
        await self._client.delete()

    @override
    async def list_head(self, *, limit: int | None = None) -> RequestQueueHead:
        return RequestQueueHead.model_validate(
            self._client.list_head(
                limit=limit,
            ),
        )

    @override
    async def list_and_lock_head(self, *, lock_secs: int, limit: int | None = None) -> dict:
        return await self._client.list_and_lock_head(
            lock_secs=lock_secs,
            limit=limit,
        )

    @override
    async def add_request(
        self,
        request: Request,
        *,
        forefront: bool = False,
    ) -> RequestQueueOperationInfo:
        return RequestQueueOperationInfo.model_validate(
            await self._client.add_request(
                request=request.model_dump(by_alias=True),
                forefront=forefront,
            )
        )

    @override
    async def get_request(self, request_id: str) -> Request | None:
        result = await self._client.get_request(request_id)
        return Request.model_validate(result) if result else None

    @override
    async def update_request(
        self,
        request: Request,
        *,
        forefront: bool = False,
    ) -> RequestQueueOperationInfo:
        return RequestQueueOperationInfo.model_validate(
            await self._client.update_request(
                request=request.model_dump(by_alias=True),
                forefront=forefront,
            )
        )

    @override
    async def delete_request(self, request_id: str) -> None:
        await self._client.delete_request(request_id)

    @override
    async def prolong_request_lock(
        self,
        request_id: str,
        *,
        forefront: bool = False,
        lock_secs: int,
    ) -> dict:
        return await self._client.prolong_request_lock(
            request_id=request_id,
            forefront=forefront,
            lock_secs=lock_secs,
        )

    @override
    async def delete_request_lock(
        self,
        request_id: str,
        *,
        forefront: bool = False,
    ) -> None:
        await self._client.delete_request_lock(
            request_id=request_id,
            forefront=forefront,
        )

    @override
    async def batch_add_requests(
        self,
        requests: list[Request],
        *,
        forefront: bool = False,
    ) -> dict:
        return await self._client.batch_add_requests(
            requests=[r.model_dump(by_alias=True) for r in requests],
            forefront=forefront,
        )

    @override
    async def batch_delete_requests(self, requests: list[Request]) -> dict:
        return await self._client.batch_delete_requests(
            requests=[r.model_dump(by_alias=True) for r in requests],
        )

    @override
    async def list_requests(
        self,
        *,
        limit: int | None = None,
        exclusive_start_id: str | None = None,
    ) -> dict:  # TODO type
        return await self._client.list_requests(
            limit=limit,
            exclusive_start_id=exclusive_start_id,
        )