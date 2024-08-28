# ruff: noqa: TCH001 TCH002 TCH003 (Pydantic)
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from apify_shared.consts import ActorJobStatus, MetaOrigin, WebhookEventType
from crawlee._utils.models import timedelta_ms
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


class ActorRunMeta(BaseModel):
    __model_config__ = ConfigDict(populate_by_name=True)

    origin: Annotated[MetaOrigin, Field()]


class ActorRunStats(BaseModel):
    __model_config__ = ConfigDict(populate_by_name=True)

    input_body_len: Annotated[int, Field(alias='inputBodyLen')]
    restart_count: Annotated[int, Field(alias='restartCount')]
    resurrect_count: Annotated[int, Field(alias='resurrectCount')]
    mem_avg_bytes: Annotated[float, Field(alias='memAvgBytes')]
    mem_max_bytes: Annotated[int, Field(alias='memMaxBytes')]
    mem_current_bytes: Annotated[int, Field(alias='memCurrentBytes')]
    cpu_avg_usage: Annotated[float, Field(alias='cpuAvgUsage')]
    cpu_max_usage: Annotated[float, Field(alias='cpuMaxUsage')]
    cpu_current_usage: Annotated[float, Field(alias='cpuCurrentUsage')]
    net_rx_bytes: Annotated[int, Field(alias='netRxBytes')]
    net_tx_bytes: Annotated[int, Field(alias='netTxBytes')]
    duration: Annotated[timedelta_ms, Field(alias='durationMillis')]
    run_time: Annotated[timedelta, Field(alias='runTimeSecs')]
    metamorph: Annotated[int, Field(alias='metamorph')]
    compute_units: Annotated[float, Field(alias='computeUnits')]


class ActorRunOptions(BaseModel):
    __model_config__ = ConfigDict(populate_by_name=True)
    build: str
    timeout: Annotated[timedelta, Field(alias='timeoutSecs')]
    memory_mbytes: Annotated[int, Field(alias='memoryMbytes')]
    disk_mbytes: Annotated[int, Field(alias='diskMbytes')]


class ActorRunUsage(BaseModel):
    __model_config__ = ConfigDict(populate_by_name=True)
    actor_compute_units: Annotated[int | None, Field(alias='ACTOR_COMPUTE_UNITS')] = None
    dataset_reads: Annotated[int | None, Field(alias='DATASET_READS')] = None
    dataset_writes: Annotated[int | None, Field(alias='DATASET_WRITES')] = None
    key_value_store_reads: Annotated[int | None, Field(alias='KEY_VALUE_STORE_READS')] = None
    key_value_store_writes: Annotated[int | None, Field(alias='KEY_VALUE_STORE_WRITES')] = None
    key_value_store_lists: Annotated[int | None, Field(alias='KEY_VALUE_STORE_LISTS')] = None
    request_queue_reads: Annotated[int | None, Field(alias='REQUEST_QUEUE_READS')] = None
    request_queue_writes: Annotated[int | None, Field(alias='REQUEST_QUEUE_WRITES')] = None
    data_transfer_internal_gbytes: Annotated[int | None, Field(alias='DATA_TRANSFER_INTERNAL_GBYTES')] = None
    data_transfer_external_gbytes: Annotated[int | None, Field(alias='DATA_TRANSFER_EXTERNAL_GBYTES')] = None
    proxy_residential_transfer_gbytes: Annotated[int | None, Field(alias='PROXY_RESIDENTIAL_TRANSFER_GBYTES')] = None
    proxy_serps: Annotated[int | None, Field(alias='PROXY_SERPS')] = None


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
    is_status_message_terminal: Annotated[bool, Field(alias='isStatusMessageTerminal')] = False
    meta: Annotated[ActorRunMeta, Field(alias='meta')]
    stats: Annotated[ActorRunStats, Field(alias='stats')]
    options: Annotated[ActorRunOptions, Field(alias='options')]
    build_id: Annotated[str, Field(alias='buildId')]
    exit_code: Annotated[int | None, Field(alias='exitCode')] = None
    default_key_value_store_id: Annotated[str, Field(alias='defaultKeyValueStoreId')]
    default_dataset_id: Annotated[str, Field(alias='defaultDatasetId')]
    default_request_queue_id: Annotated[str, Field(alias='defaultRequestQueueId')]
    build_number: Annotated[str, Field(alias='buildNumber')]
    container_url: Annotated[str, Field(alias='containerUrl')]
    is_container_server_ready: Annotated[bool, Field(alias='isContainerServerReady')] = False
    git_branch_name: Annotated[str | None, Field(alias='gitBranchName')] = None
    usage: Annotated[ActorRunUsage | None, Field(alias='usage')] = None
    usage_total_usd: Annotated[float | None, Field(alias='usageTotalUsd')] = None
    usage_usd: Annotated[float | None, Field(alias='usageUsd')] = None
