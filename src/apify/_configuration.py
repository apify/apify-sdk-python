# ruff: noqa: TCH001 TCH002 TCH003 (so that pydantic annotations work)
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
            ),
            description='ID of the Actor',
        ),
    ] = None

    actor_run_id: Annotated[
        str | None,
        Field(
            validation_alias=AliasChoices(
                'actor_run_id',
                'apify_actor_run_id',
                'apify_act_run_id',
            ),
            description='ID of the Actor run',
        ),
    ] = None

    actor_build_id: Annotated[
        str | None,
        Field(
            validation_alias=AliasChoices(
                'actor_build_id',
                'apify_actor_build_id',
            ),
            description='ID of the Actor build used in the run',
        ),
    ] = None

    actor_build_number: Annotated[
        str | None,
        Field(
            validation_alias=AliasChoices(
                'actor_build_number',
                'apify_actor_build_number',
            ),
            description='Build number of the Actor build used in the run',
        ),
    ] = None

    actor_task_id: Annotated[
        str | None,
        Field(
            validation_alias=AliasChoices(
                'actor_task_id',
                'apify_actor_task_id',
            ),
            description='ID of the Actor task. Empty if Actor is run outside of any task, e.g. directly using the API',
        ),
    ] = None

    actor_events_ws_url: Annotated[
        str | None,
        Field(
            validation_alias=AliasChoices(
                'actor_events_websocket_url',
                'apify_actor_events_ws_url',
            ),
            description='Websocket URL where Actor may listen for events from Actor platform',
        ),
    ] = None

    api_base_url: Annotated[
        str,
        Field(
            alias='apify_api_base_url',
            description='Internal URL of the Apify API. May be used to interact with the platform programmatically',
        ),
    ] = 'https://api.apify.com'

    api_public_base_url: Annotated[
        str,
        Field(
            alias='apify_api_public_base_url',
            description='Public URL of the Apify API. May be used to link to REST API resources',
        ),
    ] = 'https://api.apify.com'

    dedicated_cpus: Annotated[
        float | None,
        Field(
            alias='apify_dedicated_cpus',
            description='Number of CPU cores reserved for the actor, based on allocated memory',
        ),
    ] = None

    disable_outdated_warning: Annotated[
        bool,
        Field(
            alias='apify_disable_outdated_warning',
            description='Controls the display of outdated SDK version warnings',
        ),
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
            ),
            description='Key of the record in the default key-value store that holds the Actor input',
        ),
    ] = 'INPUT'

    input_secrets_private_key_file: Annotated[
        str | None,
        Field(
            alias='apify_input_secrets_private_key_file',
            description='Path to the secret key used to decrypt Secret inputs.',
        ),
    ] = None

    input_secrets_private_key_passphrase: Annotated[
        str | None,
        Field(
            alias='apify_input_secrets_private_key_passphrase',
            description='Passphrase for the input secret key',
        ),
    ] = None

    is_at_home: Annotated[
        bool,
        Field(
            alias='apify_is_at_home',
            description='True if the Actor is running on Apify servers',
        ),
    ] = False

    latest_sdk_version: Annotated[
        str | None,
        Field(
            alias='apify_sdk_latest_version',
            deprecated=True,
            description='Specifies the most recent release version of the Apify SDK for Javascript. Used for '
            'checking for updates.',
        ),
    ] = None

    log_format: Annotated[
        str | None,
        Field(alias='apify_log_format', deprecated=True),
    ] = None

    max_paid_dataset_items: Annotated[
        int | None,
        Field(
            alias='actor_max_paid_dataset_items',
            description='For paid-per-result Actors, the user-set limit on returned results. Do not exceed this limit',
        ),
        BeforeValidator(lambda val: val or None),
    ] = None

    meta_origin: Annotated[
        str | None,
        Field(
            alias='apify_meta_origin',
            description='Specifies how an Actor run was started',
        ),
    ] = None

    metamorph_after_sleep: Annotated[
        timedelta_ms,
        Field(
            alias='apify_metamorph_after_sleep_millis',
            description='How long the Actor needs to wait before exiting after triggering a metamorph',
        ),
    ] = timedelta(minutes=5)

    proxy_hostname: Annotated[
        str,
        Field(
            alias='apify_proxy_hostname',
            description='Hostname of the Apify proxy',
        ),
    ] = 'proxy.apify.com'

    proxy_password: Annotated[
        str | None,
        Field(
            alias='apify_proxy_password',
            description='Password to the Apify proxy',
        ),
    ] = None

    proxy_port: Annotated[
        int,
        Field(
            alias='apify_proxy_port',
            description='Port to communicate with the Apify proxy',
        ),
    ] = 8000

    proxy_status_url: Annotated[
        str,
        Field(
            alias='apify_proxy_status_url',
            description='URL for retrieving proxy status information',
        ),
    ] = 'http://proxy.apify.com'

    started_at: Annotated[
        datetime | None,
        Field(
            validation_alias=AliasChoices(
                'actor_started_at',
                'apify_started_at',
            ),
            description='Date when the Actor was started',
        ),
    ] = None

    timeout_at: Annotated[
        datetime | None,
        Field(
            validation_alias=AliasChoices(
                'actor_timeout_at',
                'apify_timeout_at',
            ),
            description='Date when the Actor will time out',
        ),
    ] = None

    standby_port: Annotated[
        int,
        Field(
            alias='actor_standby_port',
            description='TCP port for the Actor to start an HTTP server to receive messages in the Actor Standby mode',
        ),
    ] = 4322

    token: Annotated[
        str | None,
        Field(
            alias='apify_token',
            description='API token of the user who started the Actor',
        ),
    ] = None

    user_id: Annotated[
        str | None,
        Field(
            alias='apify_user_id',
            description='ID of the user who started the Actor. May differ from the Actor owner',
        ),
    ] = None

    web_server_port: Annotated[
        int,
        Field(
            validation_alias=AliasChoices(
                'actor_web_server_port',
                'apify_container_port',
            ),
            description='TCP port for the Actor to start an HTTP server on'
            'This server can be used to receive external messages or expose monitoring and control interfaces',
        ),
    ] = 4321

    web_server_url: Annotated[
        str,
        Field(
            validation_alias=AliasChoices(
                'actor_web_server_url',
                'apify_container_url',
            ),
            description='Unique public URL for accessing the Actor run web server from the outside world',
        ),
    ] = 'http://localhost:4321'

    workflow_key: Annotated[
        str | None,
        Field(
            alias='apify_workflow_key',
            description='Identifier used for grouping related runs and API calls together',
        ),
    ] = None


# Monkey-patch the base class so that it works with the extended configuration
CrawleeConfiguration.get_global_configuration = Configuration.get_global_configuration  # type: ignore
