from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from apify_shared.consts import ActorJobStatus, MetaOrigin, WebhookEventType
from crawlee._utils.models import timedelta_ms
from crawlee._utils.urls import validate_http_url

from apify._utils import docs_group


@docs_group('Data structures')
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


@docs_group('Data structures')
class ActorRunMeta(BaseModel):
    __model_config__ = ConfigDict(populate_by_name=True)

    origin: Annotated[MetaOrigin, Field()]


@docs_group('Data structures')
class ActorRunStats(BaseModel):
    __model_config__ = ConfigDict(populate_by_name=True)

    input_body_len: Annotated[int, Field(alias='inputBodyLen')]
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
    duration: Annotated[timedelta_ms | None, Field(alias='durationMillis')] = None
    run_time: Annotated[timedelta | None, Field(alias='runTimeSecs')] = None
    metamorph: Annotated[int | None, Field(alias='metamorph')] = None
    compute_units: Annotated[float, Field(alias='computeUnits')]


@docs_group('Data structures')
class ActorRunOptions(BaseModel):
    __model_config__ = ConfigDict(populate_by_name=True)

    build: str
    timeout: Annotated[timedelta, Field(alias='timeoutSecs')]
    memory_mbytes: Annotated[int, Field(alias='memoryMbytes')]
    disk_mbytes: Annotated[int, Field(alias='diskMbytes')]


@docs_group('Data structures')
class ActorRunUsage(BaseModel):
    __model_config__ = ConfigDict(populate_by_name=True)

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


@docs_group('Data structures')
class ActorRun(BaseModel):
    __model_config__ = ConfigDict(populate_by_name=True)

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
    default_key_value_store_id: Annotated[str, Field(alias='defaultKeyValueStoreId')]
    default_dataset_id: Annotated[str, Field(alias='defaultDatasetId')]
    default_request_queue_id: Annotated[str, Field(alias='defaultRequestQueueId')]
    build_number: Annotated[str | None, Field(alias='buildNumber')] = None
    container_url: Annotated[str, Field(alias='containerUrl')]
    is_container_server_ready: Annotated[bool | None, Field(alias='isContainerServerReady')] = None
    git_branch_name: Annotated[str | None, Field(alias='gitBranchName')] = None
    usage: Annotated[ActorRunUsage | None, Field(alias='usage')] = None
    usage_total_usd: Annotated[float | None, Field(alias='usageTotalUsd')] = None
    usage_usd: Annotated[ActorRunUsage | None, Field(alias='usageUsd')] = None
