from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from apify_client._models import (
    ExampleWebhookDispatch,
    WebhookCondition,
    WebhookStats,
)
from crawlee._utils.urls import validate_http_url

from apify._utils import docs_group

PricingModel = Literal['PAY_PER_EVENT', 'PRICE_PER_DATASET_ITEM', 'FLAT_PRICE_PER_MONTH', 'FREE']
"""Pricing model for an Actor."""


@docs_group('Actor')
class Webhook(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='allow')

    event_types: Annotated[
        list[str],
        Field(alias='eventTypes', description='Event types that should trigger the webhook'),
    ]
    request_url: Annotated[
        str,
        Field(alias='requestUrl', description='URL that the webhook should call'),
        BeforeValidator(validate_http_url),
    ]
    id: Annotated[str | None, Field(alias='id')] = None
    created_at: Annotated[str | None, Field(alias='createdAt')] = None
    modified_at: Annotated[str | None, Field(alias='modifiedAt')] = None
    user_id: Annotated[str | None, Field(alias='userId')] = None
    is_ad_hoc: Annotated[bool | None, Field(alias='isAdHoc')] = None
    should_interpolate_strings: Annotated[bool | None, Field(alias='shouldInterpolateStrings')] = None
    condition: Annotated[WebhookCondition | None, Field(alias='condition')] = None
    ignore_ssl_errors: Annotated[bool | None, Field(alias='ignoreSslErrors')] = None
    do_not_retry: Annotated[bool | None, Field(alias='doNotRetry')] = None
    payload_template: Annotated[
        str | None,
        Field(alias='payloadTemplate', description='Template for the payload sent by the webhook'),
    ] = None
    headers_template: Annotated[str | None, Field(alias='headersTemplate')] = None
    description: Annotated[str | None, Field(alias='description')] = None
    last_dispatch: Annotated[ExampleWebhookDispatch | None, Field(alias='lastDispatch')] = None
    stats: Annotated[WebhookStats | None, Field(alias='stats')] = None
