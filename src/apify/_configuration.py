from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from logging import getLogger
from pathlib import Path
from typing import Annotated, Any

from pydantic import AliasChoices, BeforeValidator, Field, model_validator
from typing_extensions import Self, deprecated

from crawlee import service_locator
from crawlee._utils.models import timedelta_ms
from crawlee._utils.urls import validate_http_url
from crawlee.configuration import Configuration as CrawleeConfiguration

from apify._models import (
    FlatPricePerMonthActorPricingInfo,
    FreeActorPricingInfo,
    PayPerEventActorPricingInfo,
    PricePerDatasetItemActorPricingInfo,
)
from apify._utils import docs_group

logger = getLogger(__name__)


def _transform_to_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if not value:
        return []
    return value if isinstance(value, list) else str(value).split(',')


@docs_group('Configuration')
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

    actor_full_name: Annotated[
        str | None,
        Field(
            description='Full name of the Actor',
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

    actor_build_tags: Annotated[
        list[str] | None,
        Field(
            description='Build tags of the Actor build used in the run',
        ),
        BeforeValidator(_transform_to_list),
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

    default_dataset_id: Annotated[
        str | None,
        Field(
            validation_alias=AliasChoices(
                'actor_default_dataset_id',
                'apify_default_dataset_id',
            ),
            description='Default dataset ID used by the Apify storage client when no ID or name is provided.',
        ),
    ] = None

    default_key_value_store_id: Annotated[
        str | None,
        Field(
            validation_alias=AliasChoices(
                'actor_default_key_value_store_id',
                'apify_default_key_value_store_id',
            ),
            description='Default key-value store ID for the Apify storage client when no ID or name is provided.',
        ),
    ] = None

    default_request_queue_id: Annotated[
        str | None,
        Field(
            validation_alias=AliasChoices(
                'actor_default_request_queue_id',
                'apify_default_request_queue_id',
            ),
            description='Default request queue ID for the Apify storage client when no ID or name is provided.',
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
            description='Specifies the most recent release version of the Apify SDK for Javascript. Used for '
            'checking for updates.',
        ),
        deprecated('SDK version checking is not supported for the Python SDK'),
    ] = None

    log_format: Annotated[
        str | None,
        Field(alias='apify_log_format'),
        deprecated('Adjust the log format in code instead'),
    ] = None

    max_paid_dataset_items: Annotated[
        int | None,
        Field(
            alias='actor_max_paid_dataset_items',
            description='For paid-per-result Actors, the user-set limit on returned results. Do not exceed this limit',
        ),
        BeforeValidator(lambda val: val or None),
    ] = None

    max_total_charge_usd: Annotated[
        Decimal | None,
        Field(
            alias='actor_max_total_charge_usd',
            description='For pay-per-event Actors, the user-set limit on total charges. Do not exceed this limit',
        ),
        BeforeValidator(lambda val: val or None),
    ] = None

    test_pay_per_event: Annotated[
        bool,
        Field(
            alias='actor_test_pay_per_event',
            description='Enable pay-per-event functionality for local development',
        ),
    ] = False

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
        BeforeValidator(lambda val: val if val != '' else None),  # We should accept empty environment variables as well
    ] = None

    standby_port: Annotated[
        int,
        Field(
            alias='actor_standby_port',
            description='TCP port for the Actor to start an HTTP server to receive messages in the Actor Standby mode',
        ),
        deprecated('Use `web_server_port` instead'),
    ] = 4321

    standby_url: Annotated[
        str,
        BeforeValidator(validate_http_url),
        Field(
            alias='actor_standby_url',
            description='URL for accessing web servers of Actor runs in Standby mode',
        ),
    ] = 'http://localhost'

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

    user_is_paying: Annotated[
        bool,
        Field(
            alias='apify_user_is_paying',
            description='True if the user calling the Actor is paying user',
        ),
        BeforeValidator(lambda val: False if val == '' else val),
    ] = False

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
            description='Unique public URL for accessing a specific Actor run web server from the outside world',
        ),
    ] = 'http://localhost:4321'

    workflow_key: Annotated[
        str | None,
        Field(
            alias='apify_workflow_key',
            description='Identifier used for grouping related runs and API calls together',
        ),
    ] = None

    actor_pricing_info: Annotated[
        FreeActorPricingInfo
        | FlatPricePerMonthActorPricingInfo
        | PricePerDatasetItemActorPricingInfo
        | PayPerEventActorPricingInfo
        | None,
        Field(
            alias='apify_actor_pricing_info',
            description='JSON string with prising info of the actor',
            discriminator='pricing_model',
        ),
        BeforeValidator(lambda data: json.loads(data) if isinstance(data, str) else data if data else None),
    ] = None

    charged_event_counts: Annotated[
        dict[str, int] | None,
        Field(
            alias='apify_charged_actor_event_counts',
            description='Counts of events that were charged for the actor',
        ),
        BeforeValidator(lambda data: json.loads(data) if isinstance(data, str) else data if data else None),
    ] = None

    @model_validator(mode='after')
    def disable_browser_sandbox_on_platform(self) -> Self:
        """Disable the browser sandbox mode when running on the Apify platform.

        Running in environment where `is_at_home` is True does not benefit from browser sandbox as it is already running
        in a container. It can be on the contrary undesired as the process in the container might be running as root and
        this will crash chromium that was started with browser sandbox mode.
        """
        if self.is_at_home and not self.disable_browser_sandbox:
            self.disable_browser_sandbox = True
            logger.warning('Actor is running on the Apify platform, `disable_browser_sandbox` was changed to True.')
        return self

    @property
    def canonical_input_key(self) -> str:
        return str(Path(self.input_key).with_suffix('.json'))

    @property
    def input_key_candidates(self) -> set[str]:
        return {self.input_key, self.canonical_input_key, Path(self.canonical_input_key).stem}

    @classmethod
    def get_global_configuration(cls) -> Configuration:
        """Retrieve the global instance of the configuration.

        This method ensures that ApifyConfiguration is returned, even if CrawleeConfiguration was set in the
        service locator.
        """
        global_configuration = service_locator.get_configuration()

        if isinstance(global_configuration, Configuration):
            # If Apify configuration was already stored in service locator, return it.
            return global_configuration

        logger.warning(
            'Non Apify Configuration is set in the `service_locator` in the SDK context. '
            'It is recommended to set `apify.Configuration` explicitly as early as possible by using '
            'service_locator.set_configuration'
        )

        return cls.from_configuration(global_configuration)

    @classmethod
    def from_configuration(cls, configuration: CrawleeConfiguration) -> Configuration:
        """Create Apify Configuration from existing Crawlee Configuration.

        Args:
            configuration: The existing Crawlee Configuration.

        Returns:
            The created Apify Configuration.
        """
        apify_configuration = cls()

        # Ensure the returned configuration is of type Apify Configuration.
        # Most likely crawlee configuration was already set. Create Apify configuration from it.
        # Due to known Pydantic issue https://github.com/pydantic/pydantic/issues/9516, creating new instance of
        # Configuration from existing one in situation where environment can have some fields set by alias is very
        # unpredictable. Use the stable workaround.
        for name in configuration.model_fields:
            setattr(apify_configuration, name, getattr(configuration, name))

        return apify_configuration
