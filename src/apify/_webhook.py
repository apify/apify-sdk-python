from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from apify_client._models import WebhookRepresentation
from crawlee._utils.urls import validate_http_url

from apify._utils import docs_group

if TYPE_CHECKING:
    from apify_client._literals import WebhookEventType


@docs_group('Actor')
@dataclass
class Webhook:
    """An Apify webhook definition used by the Actor SDK.

    The same instance can be passed as an ad-hoc webhook to `Actor.start()` / `Actor.call()` or as a persistent
    webhook to `Actor.add_webhook()` (the `condition.actor_run_id` is set automatically to the current run).
    """

    event_types: list[WebhookEventType]
    """Events that trigger the webhook."""

    request_url: str
    """URL the webhook sends its payload to."""

    payload_template: str | None = None
    """Template for the JSON payload sent by the webhook."""

    headers_template: str | None = None
    """Template for the HTTP headers sent by the webhook."""

    idempotency_key: str | None = None
    """Key that prevents creating duplicate webhooks."""

    ignore_ssl_errors: bool | None = None
    """Whether to ignore SSL errors when sending the request."""

    do_not_retry: bool | None = None
    """Whether to skip retrying the request on failure."""

    def __post_init__(self) -> None:
        # Fail fast on a malformed URL at construction time instead of deferring the error to the API call.
        validate_http_url(self.request_url)


def to_client_representations(webhooks: list[Webhook] | None) -> list[WebhookRepresentation] | None:
    """Project SDK webhooks to the minimal ad-hoc representation accepted by the client's `start()` / `call()`."""
    if not webhooks:
        return None
    return [
        WebhookRepresentation(
            event_types=w.event_types,
            request_url=w.request_url,
            payload_template=w.payload_template,
            headers_template=w.headers_template,
        )
        for w in webhooks
    ]
