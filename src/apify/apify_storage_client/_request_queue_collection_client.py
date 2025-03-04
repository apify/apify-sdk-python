from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from crawlee.storage_clients._base import RequestQueueCollectionClient as BaseRequestQueueCollectionClient
from crawlee.storage_clients.models import RequestQueueListPage, RequestQueueMetadata

if TYPE_CHECKING:
    from apify_client.clients import RequestQueueCollectionClientAsync


class RequestQueueCollectionClient(BaseRequestQueueCollectionClient):
    """Request queue collection resource client implementation based on the Apify platform storage."""

    def __init__(self, apify_request_queue_collection_client: RequestQueueCollectionClientAsync) -> None:
        self._client = apify_request_queue_collection_client

    @override
    async def get_or_create(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        schema: dict | None = None,
    ) -> RequestQueueMetadata:
        return RequestQueueMetadata.model_validate(
            {'resourceDirectory': ''}
            | await self._client.get_or_create(
                name=id if id is not None else name,
            )
        )

    @override
    async def list(
        self,
        *,
        unnamed: bool = False,
        limit: int | None = None,
        offset: int | None = None,
        desc: bool = False,
    ) -> RequestQueueListPage:
        return RequestQueueListPage.model_validate(
            await self._client.list(
                unnamed=unnamed,
                limit=limit,
                offset=offset,
                desc=desc,
            )
        )
