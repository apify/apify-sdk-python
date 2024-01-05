from __future__ import annotations

from apify_shared.consts import ActorEnvVars, ApifyEnvVars

from apify._utils import fetch_and_parse_env_var


class Configuration:
    """A class for specifying the configuration of an actor.

    Can be used either globally via `Configuration.get_global_configuration()`,
    or it can be specific to each `Actor` instance on the `actor.config` property.
    """

    _default_instance: Configuration | None = None

    def __init__(
        self: Configuration,
        *,
        api_base_url: str | None = None,
        api_public_base_url: str | None = None,
        container_port: int | None = None,
        container_url: str | None = None,
        default_dataset_id: str | None = None,
        default_key_value_store_id: str | None = None,
        default_request_queue_id: str | None = None,
        input_key: str | None = None,
        max_used_cpu_ratio: float | None = None,
        metamorph_after_sleep_millis: int | None = None,
        persist_state_interval_millis: int | None = None,
        persist_storage: bool | None = None,
        proxy_hostname: str | None = None,
        proxy_password: str | None = None,
        proxy_port: int | None = None,
        proxy_status_url: str | None = None,
        purge_on_start: bool | None = None,
        token: str | None = None,
        system_info_interval_millis: int | None = None,
    ) -> None:
        """Create a `Configuration` instance.

        All the parameters are loaded by default from environment variables when running on the Apify platform.
        You can override them here in the Configuration constructor, which might be useful for local testing of your actors.

        Args:
            api_base_url (str, optional): The URL of the Apify API.
                This is the URL actually used for connecting to the API, so it can contain an IP address when running in a container on the platform.
            api_public_base_url (str, optional): The public URL of the Apify API.
                This will always contain the public URL of the API, even when running in a container on the platform.
                Useful for generating shareable URLs to key-value store records or datasets.
            container_port (int, optional): The port on which the container can listen for HTTP requests.
            container_url (str, optional): The URL on which the container can listen for HTTP requests.
            default_dataset_id (str, optional): The ID of the default dataset for the actor.
            default_key_value_store_id (str, optional): The ID of the default key-value store for the actor.
            default_request_queue_id (str, optional): The ID of the default request queue for the actor.
            input_key (str, optional): The key of the input record in the actor's default key-value store
            max_used_cpu_ratio (float, optional): The CPU usage above which the SYSTEM_INFO event will report the CPU is overloaded.
            metamorph_after_sleep_millis (int, optional): How long should the actor sleep after calling metamorph.
            persist_state_interval_millis (int, optional): How often should the actor emit the PERSIST_STATE event.
            persist_storage (bool, optional): Whether the actor should persist its used storages to the filesystem when running locally.
            proxy_hostname (str, optional): The hostname of Apify Proxy.
            proxy_password (str, optional): The password for Apify Proxy.
            proxy_port (str, optional): The port of Apify Proxy.
            proxy_status_url (str, optional): The URL on which the Apify Proxy status page is available.
            purge_on_start (str, optional): Whether the actor should purge its default storages on startup, when running locally.
            token (str, optional): The API token for the Apify API this actor should use.
            system_info_interval_millis (str, optional): How often should the actor emit the SYSTEM_INFO event when running locally.
        """
        # TODO: Document all these members
        # https://github.com/apify/apify-sdk-python/issues/147
        self.actor_build_id = fetch_and_parse_env_var(ActorEnvVars.BUILD_ID)
        self.actor_build_number = fetch_and_parse_env_var(ActorEnvVars.BUILD_NUMBER)
        self.actor_events_ws_url = fetch_and_parse_env_var(ActorEnvVars.EVENTS_WEBSOCKET_URL)
        self.actor_id = fetch_and_parse_env_var(ActorEnvVars.ID)
        self.actor_run_id = fetch_and_parse_env_var(ActorEnvVars.RUN_ID)
        self.actor_task_id = fetch_and_parse_env_var(ActorEnvVars.TASK_ID)
        self.api_base_url = api_base_url or fetch_and_parse_env_var(ApifyEnvVars.API_BASE_URL, 'https://api.apify.com')
        self.api_public_base_url = api_public_base_url or fetch_and_parse_env_var(ApifyEnvVars.API_PUBLIC_BASE_URL, 'https://api.apify.com')
        self.chrome_executable_path = fetch_and_parse_env_var(ApifyEnvVars.CHROME_EXECUTABLE_PATH)
        self.container_port = container_port or fetch_and_parse_env_var(ActorEnvVars.WEB_SERVER_PORT, 4321)
        self.container_url = container_url or fetch_and_parse_env_var(ActorEnvVars.WEB_SERVER_URL, 'http://localhost:4321')
        self.dedicated_cpus = fetch_and_parse_env_var(ApifyEnvVars.DEDICATED_CPUS)
        self.default_browser_path = fetch_and_parse_env_var(ApifyEnvVars.DEFAULT_BROWSER_PATH)
        self.default_dataset_id = default_dataset_id or fetch_and_parse_env_var(ActorEnvVars.DEFAULT_DATASET_ID, 'default')
        self.default_key_value_store_id = default_key_value_store_id or fetch_and_parse_env_var(ActorEnvVars.DEFAULT_KEY_VALUE_STORE_ID, 'default')
        self.default_request_queue_id = default_request_queue_id or fetch_and_parse_env_var(ActorEnvVars.DEFAULT_REQUEST_QUEUE_ID, 'default')
        self.disable_browser_sandbox = fetch_and_parse_env_var(ApifyEnvVars.DISABLE_BROWSER_SANDBOX, default=False)
        self.headless = fetch_and_parse_env_var(ApifyEnvVars.HEADLESS, default=True)
        self.input_key = input_key or fetch_and_parse_env_var(ActorEnvVars.INPUT_KEY, 'INPUT')
        self.input_secrets_private_key_file = fetch_and_parse_env_var(ApifyEnvVars.INPUT_SECRETS_PRIVATE_KEY_FILE)
        self.input_secrets_private_key_passphrase = fetch_and_parse_env_var(ApifyEnvVars.INPUT_SECRETS_PRIVATE_KEY_PASSPHRASE)
        self.is_at_home = fetch_and_parse_env_var(ApifyEnvVars.IS_AT_HOME, default=False)
        self.max_used_cpu_ratio = max_used_cpu_ratio or fetch_and_parse_env_var(ApifyEnvVars.MAX_USED_CPU_RATIO, 0.95)
        self.memory_mbytes = fetch_and_parse_env_var(ActorEnvVars.MEMORY_MBYTES)
        self.meta_origin = fetch_and_parse_env_var(ApifyEnvVars.META_ORIGIN)
        self.metamorph_after_sleep_millis = metamorph_after_sleep_millis or fetch_and_parse_env_var(ApifyEnvVars.METAMORPH_AFTER_SLEEP_MILLIS, 300000)
        self.persist_state_interval_millis = persist_state_interval_millis or fetch_and_parse_env_var(
            ApifyEnvVars.PERSIST_STATE_INTERVAL_MILLIS, 60000
        )
        self.persist_storage = persist_storage or fetch_and_parse_env_var(ApifyEnvVars.PERSIST_STORAGE, default=True)
        self.proxy_hostname = proxy_hostname or fetch_and_parse_env_var(ApifyEnvVars.PROXY_HOSTNAME, 'proxy.apify.com')
        self.proxy_password = proxy_password or fetch_and_parse_env_var(ApifyEnvVars.PROXY_PASSWORD)
        self.proxy_port = proxy_port or fetch_and_parse_env_var(ApifyEnvVars.PROXY_PORT, 8000)
        self.proxy_status_url = proxy_status_url or fetch_and_parse_env_var(ApifyEnvVars.PROXY_STATUS_URL, 'http://proxy.apify.com')
        self.purge_on_start = purge_on_start or fetch_and_parse_env_var(ApifyEnvVars.PURGE_ON_START, default=False)
        self.started_at = fetch_and_parse_env_var(ActorEnvVars.STARTED_AT)
        self.timeout_at = fetch_and_parse_env_var(ActorEnvVars.TIMEOUT_AT)
        self.token = token or fetch_and_parse_env_var(ApifyEnvVars.TOKEN)
        self.user_id = fetch_and_parse_env_var(ApifyEnvVars.USER_ID)
        self.xvfb = fetch_and_parse_env_var(ApifyEnvVars.XVFB, default=False)
        self.system_info_interval_millis = system_info_interval_millis or fetch_and_parse_env_var(ApifyEnvVars.SYSTEM_INFO_INTERVAL_MILLIS, 60000)

    @classmethod
    def _get_default_instance(cls: type[Configuration]) -> Configuration:
        if cls._default_instance is None:
            cls._default_instance = cls()

        return cls._default_instance

    @classmethod
    def get_global_configuration(cls: type[Configuration]) -> Configuration:
        """Retrive the global configuration.

        The global configuration applies when you call actor methods via their static versions, e.g. `Actor.init()`.
        Also accessible via `Actor.config`.
        """
        return cls._get_default_instance()
