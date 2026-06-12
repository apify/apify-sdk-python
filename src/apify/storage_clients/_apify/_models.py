from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Annotated

from pydantic import AliasChoices, BaseModel, BeforeValidator, ConfigDict, Field
from pydantic.alias_generators import to_camel

from apify_client._models import RequestQueueStats
from crawlee.storage_clients.models import KeyValueStoreMetadata, RequestQueueMetadata

from apify import Request
from apify._utils import docs_group

if TYPE_CHECKING:
    from apify_client._models import LockedRequestQueueHead


@docs_group('Storage data')
class ApifyKeyValueStoreMetadata(KeyValueStoreMetadata):
    """Extended key-value store metadata model for Apify platform.

    Includes additional Apify-specific fields.
    """

    model_config = ConfigDict(alias_generator=to_camel)

    url_signing_secret_key: str | None = None
    """The secret key used for signing URLs for secure access to key-value store records."""


@docs_group('Storage data')
class RequestQueueHead(BaseModel):
    """Model for request queue head.

    Represents a collection of requests retrieved from the beginning of a queue,
    including metadata about the queue's state and lock information for the requests.
    """

    model_config = ConfigDict(populate_by_name=True, extra='allow', alias_generator=to_camel)

    limit: int | None = None
    """The maximum number of requests that were requested from the queue."""

    had_multiple_clients: bool = False
    """Indicates whether the queue has been accessed by multiple clients (consumers)."""

    queue_modified_at: datetime
    """The timestamp when the queue was last modified."""

    lock_time: Annotated[
        timedelta | None,
        Field(validation_alias=AliasChoices('lockSecs', 'lockTime'), serialization_alias='lockSecs'),
    ] = None
    """The duration for which the returned requests are locked and cannot be processed by other clients.

    The platform's API names this field `lockSecs`, so it is serialized under that alias instead of the
    `lockTime` that `to_camel` would derive from the field name.
    """

    queue_has_locked_requests: bool | None = False
    """Indicates whether the queue contains any locked requests."""

    items: Annotated[list[Request], Field(default_factory=list[Request])]
    """The list of request objects retrieved from the beginning of the queue."""

    @classmethod
    def from_client_locked_head(cls, client_locked_head: LockedRequestQueueHead) -> RequestQueueHead:
        """Create a `RequestQueueHead` from an Apify API client's `LockedRequestQueueHead` model.

        Args:
            client_locked_head: `LockedRequestQueueHead` instance from Apify API client.

        Returns:
            `RequestQueueHead` instance with properly converted types.
        """
        # Dump to dict with mode='json' to serialize special types like AnyUrl
        head_dict = client_locked_head.model_dump(by_alias=True, mode='json')

        # Validate and construct RequestQueueHead from the serialized dict
        return cls.model_validate(head_dict)


class CachedRequest(BaseModel):
    """Pydantic model for cached request information.

    Only internal structure.
    """

    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    id: str
    """Id of the request."""

    was_already_handled: bool
    """Whether the request was already handled."""

    hydrated: Request | None = None
    """The hydrated request object (the original one)."""

    lock_expires_at: datetime | None = None
    """The expiration time of the lock on the request."""


class ApifyRequestQueueMetadata(RequestQueueMetadata):
    model_config = ConfigDict(alias_generator=to_camel)

    stats: Annotated[
        RequestQueueStats,
        BeforeValidator(lambda value: RequestQueueStats() if value is None else value),
        Field(default_factory=RequestQueueStats),
    ]
    """Additional statistics about the request queue.

    The API may omit the stats (sending an explicit `null`), so a `None` value is coerced to a default
    `RequestQueueStats` rather than failing validation.
    """
