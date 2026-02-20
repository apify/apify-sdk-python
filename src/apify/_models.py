from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from apify_shared.consts import ActorJobStatus, MetaOrigin, WebhookEventType
from crawlee._utils.urls import validate_http_url

from apify._utils import docs_group

PricingModel = Literal['PAY_PER_EVENT', 'PRICE_PER_DATASET_ITEM', 'FLAT_PRICE_PER_MONTH', 'FREE']
"""Pricing model for an Actor."""

GeneralAccess = Literal['ANYONE_WITH_ID_CAN_READ', 'ANYONE_WITH_NAME_CAN_READ', 'FOLLOW_USER_SETTING', 'RESTRICTED']
"""Defines the general access level for the resource."""


class WebhookCondition(BaseModel):
    """Condition for triggering a webhook."""

    model_config = ConfigDict(populate_by_name=True, extra='allow')

    actor_id: Annotated[str | None, Field(alias='actorId')] = None
    actor_task_id: Annotated[str | None, Field(alias='actorTaskId')] = None
    actor_run_id: Annotated[str | None, Field(alias='actorRunId')] = None


WebhookDispatchStatus = Literal['ACTIVE', 'SUCCEEDED', 'FAILED']
"""Status of a webhook dispatch."""


class ExampleWebhookDispatch(BaseModel):
    """Information about a webhook dispatch."""

    model_config = ConfigDict(populate_by_name=True, extra='allow')

    status: WebhookDispatchStatus
    finished_at: Annotated[datetime, Field(alias='finishedAt')]


class WebhookStats(BaseModel):
    """Statistics about webhook dispatches."""

    model_config = ConfigDict(populate_by_name=True, extra='allow')

    total_dispatches: Annotated[int, Field(alias='totalDispatches')]


@docs_group('Actor')
class Webhook(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='allow')

    event_types: Annotated[
        list[WebhookEventType],
        Field(alias='eventTypes', description='Event types that should trigger the webhook'),
    ]
    request_url: Annotated[
        str,
        Field(alias='requestUrl', description='URL that the webhook should call'),
        BeforeValidator(validate_http_url),
    ]
    id: Annotated[str | None, Field(alias='id')] = None
    created_at: Annotated[datetime | None, Field(alias='createdAt')] = None
    modified_at: Annotated[datetime | None, Field(alias='modifiedAt')] = None
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


@docs_group('Actor')
class ActorRunMeta(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='allow')

    origin: Annotated[MetaOrigin, Field()]
    client_ip: Annotated[str | None, Field(alias='clientIp')] = None
    user_agent: Annotated[str | None, Field(alias='userAgent')] = None
    schedule_id: Annotated[str | None, Field(alias='scheduleId')] = None
    scheduled_at: Annotated[datetime | None, Field(alias='scheduledAt')] = None


@docs_group('Actor')
class ActorRunStats(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='allow')

    input_body_len: Annotated[int | None, Field(alias='inputBodyLen')] = None
    migration_count: Annotated[int | None, Field(alias='migrationCount')] = None
    reboot_count: Annotated[int | None, Field(alias='rebootCount')] = None
    restart_count: Annotated[int, Field(alias='restartCount')]
    resurrect_count: Annotated[int, Field(alias='resurrectCount')]
    mem_avg_bytes: Annotated[float | None, Field(alias='memAvgBytes')] = None
    mem_max_bytes: Annotated[int | None, Field(alias='memMaxBytes')] = None
    mem_current_bytes: Annotated[int | None, Field(alias='memCurrentBytes')] = None
    cpu_avg_usage: Annotated[float | None, Field(alias='cpuAvgUsage')] = None
    cpu_max_usage: Annotated[float | None, Field(alias='cpuMaxUsage')] = None
    cpu_current_usage: Annotated[float | None, Field(alias='cpuCurrentUsage')] = None
    net_rx_bytes: Annotated[int | None, Field(alias='netRxBytes')] = None
    net_tx_bytes: Annotated[int | None, Field(alias='netTxBytes')] = None
    duration_millis: Annotated[int | None, Field(alias='durationMillis')] = None
    run_time_secs: Annotated[float | None, Field(alias='runTimeSecs')] = None
    metamorph: Annotated[int | None, Field(alias='metamorph')] = None
    compute_units: Annotated[float, Field(alias='computeUnits')]


@docs_group('Actor')
class ActorRunOptions(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='allow')

    build: str
    timeout_secs: Annotated[int, Field(alias='timeoutSecs')]
    memory_mbytes: Annotated[int, Field(alias='memoryMbytes')]
    disk_mbytes: Annotated[int, Field(alias='diskMbytes')]
    max_items: Annotated[int | None, Field(alias='maxItems')] = None
    max_total_charge_usd: Annotated[float | None, Field(alias='maxTotalChargeUsd')] = None


@docs_group('Actor')
class ActorRunUsage(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='allow')

    actor_compute_units: Annotated[float | None, Field(alias='ACTOR_COMPUTE_UNITS')] = None
    dataset_reads: Annotated[int | None, Field(alias='DATASET_READS')] = None
    dataset_writes: Annotated[int | None, Field(alias='DATASET_WRITES')] = None
    key_value_store_reads: Annotated[int | None, Field(alias='KEY_VALUE_STORE_READS')] = None
    key_value_store_writes: Annotated[int | None, Field(alias='KEY_VALUE_STORE_WRITES')] = None
    key_value_store_lists: Annotated[int | None, Field(alias='KEY_VALUE_STORE_LISTS')] = None
    request_queue_reads: Annotated[int | None, Field(alias='REQUEST_QUEUE_READS')] = None
    request_queue_writes: Annotated[int | None, Field(alias='REQUEST_QUEUE_WRITES')] = None
    data_transfer_internal_gbytes: Annotated[float | None, Field(alias='DATA_TRANSFER_INTERNAL_GBYTES')] = None
    data_transfer_external_gbytes: Annotated[float | None, Field(alias='DATA_TRANSFER_EXTERNAL_GBYTES')] = None
    proxy_residential_transfer_gbytes: Annotated[float | None, Field(alias='PROXY_RESIDENTIAL_TRANSFER_GBYTES')] = None
    proxy_serps: Annotated[int | None, Field(alias='PROXY_SERPS')] = None


@docs_group('Actor')
class ActorRunUsageUsd(BaseModel):
    """Resource usage costs in USD."""

    model_config = ConfigDict(populate_by_name=True, extra='allow')

    actor_compute_units: Annotated[float | None, Field(alias='ACTOR_COMPUTE_UNITS')] = None
    dataset_reads: Annotated[float | None, Field(alias='DATASET_READS')] = None
    dataset_writes: Annotated[float | None, Field(alias='DATASET_WRITES')] = None
    key_value_store_reads: Annotated[float | None, Field(alias='KEY_VALUE_STORE_READS')] = None
    key_value_store_writes: Annotated[float | None, Field(alias='KEY_VALUE_STORE_WRITES')] = None
    key_value_store_lists: Annotated[float | None, Field(alias='KEY_VALUE_STORE_LISTS')] = None
    request_queue_reads: Annotated[float | None, Field(alias='REQUEST_QUEUE_READS')] = None
    request_queue_writes: Annotated[float | None, Field(alias='REQUEST_QUEUE_WRITES')] = None
    data_transfer_internal_gbytes: Annotated[float | None, Field(alias='DATA_TRANSFER_INTERNAL_GBYTES')] = None
    data_transfer_external_gbytes: Annotated[float | None, Field(alias='DATA_TRANSFER_EXTERNAL_GBYTES')] = None
    proxy_residential_transfer_gbytes: Annotated[float | None, Field(alias='PROXY_RESIDENTIAL_TRANSFER_GBYTES')] = None
    proxy_serps: Annotated[float | None, Field(alias='PROXY_SERPS')] = None


class Metamorph(BaseModel):
    """Information about a metamorph event that occurred during the run."""

    model_config = ConfigDict(populate_by_name=True, extra='allow')

    created_at: Annotated[datetime, Field(alias='createdAt')]
    actor_id: Annotated[str, Field(alias='actorId')]
    build_id: Annotated[str, Field(alias='buildId')]
    input_key: Annotated[str | None, Field(alias='inputKey')] = None


class CommonActorPricingInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='allow')

    apify_margin_percentage: Annotated[float | None, Field(alias='apifyMarginPercentage')] = None
    created_at: Annotated[datetime | None, Field(alias='createdAt')] = None
    started_at: Annotated[datetime | None, Field(alias='startedAt')] = None
    notified_about_future_change_at: Annotated[datetime | None, Field(alias='notifiedAboutFutureChangeAt')] = None
    notified_about_change_at: Annotated[datetime | None, Field(alias='notifiedAboutChangeAt')] = None
    reason_for_change: Annotated[str | None, Field(alias='reasonForChange')] = None


class FreeActorPricingInfo(CommonActorPricingInfo):
    pricing_model: Annotated[Literal['FREE'], Field(alias='pricingModel')]


class FlatPricePerMonthActorPricingInfo(CommonActorPricingInfo):
    pricing_model: Annotated[Literal['FLAT_PRICE_PER_MONTH'], Field(alias='pricingModel')]
    trial_minutes: Annotated[int, Field(alias='trialMinutes')]
    price_per_unit_usd: Annotated[float, Field(alias='pricePerUnitUsd')]


class PricePerDatasetItemActorPricingInfo(CommonActorPricingInfo):
    pricing_model: Annotated[Literal['PRICE_PER_DATASET_ITEM'], Field(alias='pricingModel')]
    unit_name: Annotated[str, Field(alias='unitName')]
    price_per_unit_usd: Annotated[float, Field(alias='pricePerUnitUsd')]


class ActorChargeEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='allow')

    event_price_usd: Annotated[float, Field(alias='eventPriceUsd')]
    event_title: Annotated[str, Field(alias='eventTitle')]
    event_description: Annotated[str | None, Field(alias='eventDescription')] = None


class PricingPerEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='allow')

    actor_charge_events: Annotated[dict[str, ActorChargeEvent] | None, Field(alias='actorChargeEvents')] = None


class PayPerEventActorPricingInfo(CommonActorPricingInfo):
    pricing_model: Annotated[Literal['PAY_PER_EVENT'], Field(alias='pricingModel')]
    pricing_per_event: Annotated[PricingPerEvent, Field(alias='pricingPerEvent')]
    minimal_max_total_charge_usd: Annotated[float | None, Field(alias='minimalMaxTotalChargeUsd')] = None


@docs_group('Actor')
class ActorRun(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='allow')

    id: Annotated[str, Field(alias='id')]
    act_id: Annotated[str, Field(alias='actId')]
    user_id: Annotated[str, Field(alias='userId')]
    actor_task_id: Annotated[str | None, Field(alias='actorTaskId')] = None
    started_at: Annotated[datetime, Field(alias='startedAt')]
    finished_at: Annotated[datetime | None, Field(alias='finishedAt')] = None
    status: Annotated[ActorJobStatus, Field(alias='status')]
    status_message: Annotated[str | None, Field(alias='statusMessage')] = None
    is_status_message_terminal: Annotated[bool | None, Field(alias='isStatusMessageTerminal')] = None
    meta: Annotated[ActorRunMeta, Field(alias='meta')]
    stats: Annotated[ActorRunStats, Field(alias='stats')]
    options: Annotated[ActorRunOptions, Field(alias='options')]
    build_id: Annotated[str, Field(alias='buildId')]
    exit_code: Annotated[int | None, Field(alias='exitCode')] = None
    general_access: Annotated[str | None, Field(alias='generalAccess')] = None
    default_key_value_store_id: Annotated[str, Field(alias='defaultKeyValueStoreId')]
    default_dataset_id: Annotated[str, Field(alias='defaultDatasetId')]
    default_request_queue_id: Annotated[str, Field(alias='defaultRequestQueueId')]
    build_number: Annotated[str | None, Field(alias='buildNumber')] = None
    container_url: Annotated[str | None, Field(alias='containerUrl')] = None
    is_container_server_ready: Annotated[bool | None, Field(alias='isContainerServerReady')] = None
    git_branch_name: Annotated[str | None, Field(alias='gitBranchName')] = None
    usage: Annotated[ActorRunUsage | None, Field(alias='usage')] = None
    usage_total_usd: Annotated[float | None, Field(alias='usageTotalUsd')] = None
    usage_usd: Annotated[ActorRunUsageUsd | None, Field(alias='usageUsd')] = None
    pricing_info: Annotated[
        FreeActorPricingInfo
        | FlatPricePerMonthActorPricingInfo
        | PricePerDatasetItemActorPricingInfo
        | PayPerEventActorPricingInfo
        | None,
        Field(alias='pricingInfo', discriminator='pricing_model'),
    ] = None
    charged_event_counts: Annotated[
        dict[str, int] | None,
        Field(alias='chargedEventCounts'),
    ] = None
    metamorphs: Annotated[list[Metamorph] | None, Field(alias='metamorphs')] = None
