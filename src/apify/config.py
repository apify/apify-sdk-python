# ruff: noqa: TCH002 TCH003
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from crawlee._utils.models import timedelta_ms
from crawlee.configuration import Configuration as CrawleeConfiguration
from pydantic import Field
from typing_extensions import Self


class Configuration(CrawleeConfiguration):
    """A class for specifying the configuration of an actor.

    Can be used either globally via `Configuration.get_global_configuration()`,
    or it can be specific to each `Actor` instance on the `actor.config` property.
    """

    actor_id: Annotated[str | None, Field(alias='actor_id')] = None
    actor_run_id: Annotated[str | None, Field(alias='actor_run_id')] = None
    actor_build_id: Annotated[str | None, Field()] = None
    actor_build_number: Annotated[str | None, Field()] = None
    actor_task_id: Annotated[str | None, Field(alias='actor_task_id')] = None
    actor_events_ws_url: Annotated[str | None, Field(alias='actor_events_websocket_url')] = None
    api_base_url: Annotated[str, Field(alias='apify_api_base_url')] = 'https://api.apify.com'
    api_public_base_url: Annotated[str, Field(alias='apify_api_public_base_url')] = 'https://api.apify.com'
    default_dataset_id: Annotated[str, Field(alias='actor_default_dataset_id')] = 'default'
    default_key_value_store_id: Annotated[str, Field(alias='actor_default_key_value_store_id')] = 'default'
    default_request_queue_id: Annotated[str, Field(alias='actor_default_request_queue_id')] = 'default'
    disable_browser_sandbox: Annotated[bool, Field(alias='apify_disable_browser_sandbox')] = False
    headless: Annotated[bool, Field(alias='apify_headless')] = True
    input_key: Annotated[str, Field(alias='actor_input_key')] = 'INPUT'
    input_secrets_private_key_file: Annotated[str | None, Field(alias='apify_input_secrets_private_key_file')] = None
    input_secrets_private_key_passphrase: Annotated[str | None, Field(alias='apify_input_secrets_private_key_passphrase')] = None
    is_at_home: Annotated[bool, Field(alias='apify_is_at_home')] = False
    max_paid_dataset_items: Annotated[int | None, Field(alias='actor_max_paid_dataset_items')] = None
    memory_mbytes: Annotated[int | None, Field(alias='actor_memory_mbytes')] = None
    meta_origin: Annotated[str | None, Field(alias='apify_meta_origin')] = None
    metamorph_after_sleep: Annotated[timedelta_ms, Field('apify_metamorph_after_sleep_millis')] = timedelta(minutes=5)
    persist_state_interval: Annotated[timedelta_ms, Field('apify_persist_state_interval_millis')] = timedelta(minutes=1)
    persist_storage: Annotated[bool, Field(alias='apify_persist_storage')] = True
    proxy_hostname: Annotated[str, Field(alias='apify_proxy_hostname')] = 'proxy.apify.com'
    proxy_password: Annotated[str | None, Field(alias='apify_proxy_password')] = None
    proxy_port: Annotated[int, Field(alias='apify_proxy_port')] = 8000
    proxy_status_url: Annotated[str, Field(alias='apify_proxy_status_url')] = 'http://proxy.apify.com'
    purge_on_start: Annotated[bool, Field(alias='apify_purge_on_start')] = False
    started_at: Annotated[datetime | None, Field(alias='actor_started_at')] = None
    timeout_at: Annotated[datetime | None, Field(alias='actor_timeout_at')] = None
    token: Annotated[str | None, Field(alias='apify_token')] = None
    user_id: Annotated[str | None, Field(alias='apify_user_id')] = None
    web_server_port: Annotated[int, Field(alias='actor_web_server_port')] = 4321
    web_server_url: Annotated[str, Field(alias='actor_web_server_url')] = 'http://localhost:4321'
    xvfb: Annotated[bool, Field(alias='apify_xvfb')] = False
    system_info_interval: Annotated[timedelta_ms, Field(alias='apify_system_info_interval_millis')] = timedelta(minutes=1)

    # TODO chrome_executable_path, container_port, container_url, dedicated_cpus, default_browser_path,
    # disable_browser_sandbox, input_secrets_private_key_file, input_secrets_private_key_passphrase, max_used_cpu_ratio

    @classmethod
    def get_global_configuration(cls) -> Self:
        """Retrive the global configuration.

        The global configuration applies when you call actor methods via their static versions, e.g. `Actor.init()`.
        Also accessible via `Actor.config`.
        """
        if cls._default_instance is None:
            cls._default_instance = cls()

        return cls._default_instance
