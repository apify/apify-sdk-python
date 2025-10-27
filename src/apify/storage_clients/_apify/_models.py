from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from crawlee.storage_clients.models import KeyValueStoreMetadata, RequestQueueMetadata

from apify import Request
from apify._utils import docs_group


@docs_group('Storage data')
class ApifyKeyValueStoreMetadata(KeyValueStoreMetadata):
    """Extended key-value store metadata model for Apify platform.

    Includes additional Apify-specific fields.
    """

    url_signing_secret_key: Annotated[str | None, Field(alias='urlSigningSecretKey', default=None)]
    """The secret key used for signing URLs for secure access to key-value store records."""


@docs_group('Storage data')
class ProlongRequestLockResponse(BaseModel):
    """Response to prolong request lock calls."""

    model_config = ConfigDict(populate_by_name=True)

    lock_expires_at: Annotated[datetime, Field(alias='lockExpiresAt')]


@docs_group('Storage data')
class RequestQueueHead(BaseModel):
    """Model for request queue head.

    Represents a collection of requests retrieved from the beginning of a queue,
    including metadata about the queue's state and lock information for the requests.
    """

    model_config = ConfigDict(populate_by_name=True)

    limit: Annotated[int | None, Field(alias='limit', default=None)]
    """The maximum number of requests that were requested from the queue."""

    had_multiple_clients: Annotated[bool, Field(alias='hadMultipleClients', default=False)]
    """Indicates whether the queue has been accessed by multiple clients (consumers)."""

    queue_modified_at: Annotated[datetime, Field(alias='queueModifiedAt')]
    """The timestamp when the queue was last modified."""

    lock_time: Annotated[timedelta | None, Field(alias='lockSecs', default=None)]
    """The duration for which the returned requests are locked and cannot be processed by other clients."""

    queue_has_locked_requests: Annotated[bool | None, Field(alias='queueHasLockedRequests', default=False)]
    """Indicates whether the queue contains any locked requests."""

    items: Annotated[list[Request], Field(alias='items', default_factory=list[Request])]
    """The list of request objects retrieved from the beginning of the queue."""


class KeyValueStoreKeyInfo(BaseModel):
    """Model for a key-value store key info.

    Only internal structure.
    """

    model_config = ConfigDict(populate_by_name=True)

    key: Annotated[str, Field(alias='key')]
    size: Annotated[int, Field(alias='size')]


class KeyValueStoreListKeysPage(BaseModel):
    """Model for listing keys in the key-value store.

    Only internal structure.
    """

    model_config = ConfigDict(populate_by_name=True)

    count: Annotated[int, Field(alias='count')]
    limit: Annotated[int, Field(alias='limit')]
    is_truncated: Annotated[bool, Field(alias='isTruncated')]
    items: Annotated[list[KeyValueStoreKeyInfo], Field(alias='items', default_factory=list)]
    exclusive_start_key: Annotated[str | None, Field(alias='exclusiveStartKey', default=None)]
    next_exclusive_start_key: Annotated[str | None, Field(alias='nextExclusiveStartKey', default=None)]


class CachedRequest(BaseModel):
    """Pydantic model for cached request information.

    Only internal structure.
    """

    id: str
    """Id of the request."""

    was_already_handled: bool
    """Whether the request was already handled."""

    hydrated: Request | None = None
    """The hydrated request object (the original one)."""

    lock_expires_at: datetime | None = None
    """The expiration time of the lock on the request."""


class RequestQueueStats(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    delete_count: Annotated[int, Field(alias='deleteCount', default=0)]
    """"The number of request queue deletes."""

    head_item_read_count: Annotated[int, Field(alias='headItemReadCount', default=0)]
    """The number of request queue head reads."""

    read_count: Annotated[int, Field(alias='readCount', default=0)]
    """The number of request queue reads."""

    storage_bytes: Annotated[int, Field(alias='storageBytes', default=0)]
    """Storage size in bytes."""

    write_count: Annotated[int, Field(alias='writeCount', default=0)]
    """The number of request queue writes."""


class ApifyRequestQueueMetadata(RequestQueueMetadata):
    stats: Annotated[RequestQueueStats, Field(alias='stats', default_factory=RequestQueueStats)]
    """Additional statistics about the request queue."""
