from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from apify_client._models import WebhookRepresentation
from crawlee._utils.urls import validate_http_url

from apify._utils import docs_group
from apify.log import logger

if TYPE_CHECKING:
    from apify_client._literals import WebhookEventType


@docs_group('Actor')
@dataclass
class Webhook:
    """An Apify webhook definition used by the Actor SDK.

    The same instance can be passed as an ad-hoc webhook to `Actor.start()` / `Actor.call()` or as a persistent
    webhook to `Actor.add_webhook()` (the `condition.actor_run_id` is set automatically to the current run).

    Ad-hoc webhooks support only `event_types`, `request_url`, `payload_template` and `headers_template`; the
    remaining fields apply only to `Actor.add_webhook()` and are ignored (with a warning) otherwise.
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
    """Key that prevents creating duplicate webhooks. Only applies to `Actor.add_webhook()`."""

    ignore_ssl_errors: bool | None = None
    """Whether to ignore SSL errors when sending the request. Only applies to `Actor.add_webhook()`."""

    do_not_retry: bool | None = None
    """Whether to skip retrying the request on failure. Only applies to `Actor.add_webhook()`."""

    def __post_init__(self) -> None:
        # Fail fast on a malformed URL at construction time instead of deferring the error to the API call.
        validate_http_url(self.request_url)


def to_client_representations(webhooks: list[Webhook] | None) -> list[WebhookRepresentation] | None:
    """Project SDK webhooks to the minimal ad-hoc representation accepted by the client's `start()` / `call()`.

    Fields not supported by ad-hoc webhooks (`idempotency_key`, `ignore_ssl_errors`, `do_not_retry`) are dropped
    with a warning.
    """
    if not webhooks:
        return None

    for webhook in webhooks:
        dropped = [
            field
            for field in ('idempotency_key', 'ignore_ssl_errors', 'do_not_retry')
            if getattr(webhook, field) is not None
        ]
        if dropped:
            fields = ', '.join(f'`{field}`' for field in dropped)
            logger.warning(
                f'Ad-hoc webhooks do not support {fields}; the field(s) will be ignored. '
                f'Use `Actor.add_webhook()` to create a webhook with them.'
            )

    return [
        WebhookRepresentation(
            event_types=w.event_types,
            request_url=w.request_url,
            payload_template=w.payload_template,
            headers_template=w.headers_template,
        )
        for w in webhooks
    ]
