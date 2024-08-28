# ruff: noqa: TCH001 TCH002 TCH003 (Pydantic)
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from apify_shared.consts import WebhookEventType
from crawlee._utils.urls import validate_http_url


class Webhook(BaseModel):
    __model_config__ = ConfigDict(populate_by_name=True)

    event_types: Annotated[
        list[WebhookEventType],
        Field(description='Event types that should trigger the webhook'),
    ]
    request_url: Annotated[
        str,
        Field(description='URL that the webhook should call'),
        BeforeValidator(validate_http_url),
    ]
    payload_template: Annotated[
        str | None,
        Field(description='Template for the payload sent by the webook'),
    ] = None
