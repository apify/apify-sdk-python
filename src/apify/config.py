# ruff: noqa: TCH001 TCH002 TCH003
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from pydantic import AliasChoices, BeforeValidator, Field

from crawlee._utils.models import timedelta_ms
from crawlee.configuration import Configuration as CrawleeConfiguration


class Configuration(CrawleeConfiguration):
    """A class for specifying the configuration of an Actor.

    Can be used either globally via `Configuration.get_global_configuration()`,
    or it can be specific to each `Actor` instance on the `actor.config` property.
    """

    actor_id: Annotated[
        str | None,
        Field(
            validation_alias=AliasChoices(
                'actor_id',
                'apify_actor_id',
                'apify_act_id',
            )
        ),
    ] = None

    actor_run_id: Annotated[
        str | None,
        Field(
            validation_alias=AliasChoices(
                'actor_run_id',
                'apify_actor_run_id',
                'apify_act_run_id',
            )
        ),
    ] = None

    actor_build_id: Annotated[
        str | None,
        Field(
            validation_alias=AliasChoices(
                'actor_build_id',
                'apify_actor_build_id',
            )
        ),
    ] = None

    actor_build_number: Annotated[
        str | None,
        Field(
            validation_alias=AliasChoices(
                'actor_build_number',
                'apify_actor_build_number',
            )
        ),
    ] = None

    actor_task_id: Annotated[
        str | None,
        Field(
            validation_alias=AliasChoices(
                'actor_task_id',
                'apify_actor_task_id',
            )
        ),
    ] = None

    actor_events_ws_url: Annotated[
        str | None,
        Field(
            validation_alias=AliasChoices(
                'actor_events_websocket_url',
                'apify_actor_events_ws_url',
            )
        ),
    ] = None

    api_base_url: Annotated[str, Field(alias='apify_api_base_url')] = 'https://api.apify.com'

    api_public_base_url: Annotated[str, Field(alias='apify_api_public_base_url')] = 'https://api.apify.com'

    dedicated_cpus: Annotated[float | None, Field(alias='apify_dedicated_cpus')] = None

    disable_outdated_warning: Annotated[
        bool,
        Field(alias='apify_disable_outdated_warning'),
        BeforeValidator(lambda val: val or False),
    ] = False

    fact: Annotated[str | None, Field(alias='apify_fact')] = None

    input_key: Annotated[
        str,
        Field(
            validation_alias=AliasChoices(
                'actor_input_key',
                'apify_input_key',
                'crawlee_input_key',
            )
        ),
    ] = 'INPUT'

    input_secrets_private_key_file: Annotated[str | None, Field(alias='apify_input_secrets_private_key_file')] = None

    input_secrets_private_key_passphrase: Annotated[str | None, Field(alias='apify_input_secrets_private_key_passphrase')] = None

    is_at_home: Annotated[bool, Field(alias='apify_is_at_home')] = False

    latest_sdk_version: Annotated[str | None, Field(alias='apify_sdk_latest_version', deprecated=True)] = None

    log_format: Annotated[str | None, Field(alias='apify_log_format', deprecated=True)] = None

    max_paid_dataset_items: Annotated[
        int | None,
        Field(alias='actor_max_paid_dataset_items'),
        BeforeValidator(lambda val: val or None),
    ] = None

    meta_origin: Annotated[str | None, Field(alias='apify_meta_origin')] = None

    metamorph_after_sleep: Annotated[timedelta_ms, Field(alias='apify_metamorph_after_sleep_millis')] = timedelta(minutes=5)

    proxy_hostname: Annotated[str, Field(alias='apify_proxy_hostname')] = 'proxy.apify.com'

    proxy_password: Annotated[str | None, Field(alias='apify_proxy_password')] = None

    proxy_port: Annotated[int, Field(alias='apify_proxy_port')] = 8000

    proxy_status_url: Annotated[str, Field(alias='apify_proxy_status_url')] = 'http://proxy.apify.com'

    started_at: Annotated[
        datetime | None,
        Field(
            validation_alias=AliasChoices(
                'actor_started_at',
                'apify_started_at',
            )
        ),
    ] = None

    timeout_at: Annotated[
        datetime | None,
        Field(
            validation_alias=AliasChoices(
                'actor_timeout_at',
                'apify_timeout_at',
            )
        ),
    ] = None

    standby_port: Annotated[int, Field(alias='actor_standby_port')] = 4322

    token: Annotated[str | None, Field(alias='apify_token')] = None

    user_id: Annotated[str | None, Field(alias='apify_user_id')] = None

    web_server_port: Annotated[
        int,
        Field(
            validation_alias=AliasChoices(
                'actor_web_server_port',
                'apify_container_port',
            )
        ),
    ] = 4321

    web_server_url: Annotated[
        str,
        Field(
            validation_alias=AliasChoices(
                'actor_web_server_url',
                'apify_container_url',
            )
        ),
    ] = 'http://localhost:4321'

    workflow_key: Annotated[str | None, Field(alias='apify_workflow_key')] = None


# Monkey-patch the base class so that it works with the extended configuration
CrawleeConfiguration.get_global_configuration = Configuration.get_global_configuration  # type: ignore
