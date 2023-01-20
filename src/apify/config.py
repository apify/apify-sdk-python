from typing import Optional

from ._utils import _fetch_and_parse_env_var
from .consts import ApifyEnvVars


class Configuration:
    """A class for specifying the configuration of an actor.

    Can be used either globally via `Configuration.get_global_configuration()`,
    or it can be specific to each `Actor` instance on the `actor.config` property.
    """

    _default_instance: Optional['Configuration'] = None

    def __init__(self) -> None:
        """Create a `Configuration` instance."""
        self.actor_build_id = _fetch_and_parse_env_var(ApifyEnvVars.ACTOR_BUILD_ID)
        self.actor_build_number = _fetch_and_parse_env_var(ApifyEnvVars.ACTOR_BUILD_NUMBER)
        self.actor_events_ws_url = _fetch_and_parse_env_var(ApifyEnvVars.ACTOR_EVENTS_WS_URL)
        self.actor_id = _fetch_and_parse_env_var(ApifyEnvVars.ACTOR_ID)
        self.actor_run_id = _fetch_and_parse_env_var(ApifyEnvVars.ACTOR_RUN_ID)
        self.actor_task_id = _fetch_and_parse_env_var(ApifyEnvVars.ACTOR_TASK_ID)
        self.api_base_url = _fetch_and_parse_env_var(ApifyEnvVars.API_BASE_URL, 'https://api.apify.com')
        self.api_public_base_url = _fetch_and_parse_env_var(ApifyEnvVars.API_PUBLIC_BASE_URL, 'https://api.apify.com')
        self.chrome_executable_path = _fetch_and_parse_env_var(ApifyEnvVars.CHROME_EXECUTABLE_PATH)
        self.container_port = _fetch_and_parse_env_var(ApifyEnvVars.CONTAINER_PORT, 4321)
        self.container_url = _fetch_and_parse_env_var(ApifyEnvVars.CONTAINER_URL, 'http://localhost:4321')
        self.dedicated_cpus = _fetch_and_parse_env_var(ApifyEnvVars.DEDICATED_CPUS)
        self.default_browser_path = _fetch_and_parse_env_var(ApifyEnvVars.DEFAULT_BROWSER_PATH)
        self.default_dataset_id = _fetch_and_parse_env_var(ApifyEnvVars.DEFAULT_DATASET_ID, 'default')
        self.default_key_value_store_id = _fetch_and_parse_env_var(ApifyEnvVars.DEFAULT_KEY_VALUE_STORE_ID, 'default')
        self.default_request_queue_id = _fetch_and_parse_env_var(ApifyEnvVars.DEFAULT_REQUEST_QUEUE_ID, 'default')
        self.disable_browser_sandbox = _fetch_and_parse_env_var(ApifyEnvVars.DISABLE_BROWSER_SANDBOX, False)
        self.headless = _fetch_and_parse_env_var(ApifyEnvVars.HEADLESS, True)
        self.input_key = _fetch_and_parse_env_var(ApifyEnvVars.INPUT_KEY, 'INPUT')
        self.input_secrets_private_key_file = _fetch_and_parse_env_var(ApifyEnvVars.INPUT_SECRETS_PRIVATE_KEY_FILE)
        self.input_secrets_private_key_passphrase = _fetch_and_parse_env_var(ApifyEnvVars.INPUT_SECRETS_PRIVATE_KEY_PASSPHRASE)
        self.is_at_home = _fetch_and_parse_env_var(ApifyEnvVars.IS_AT_HOME, False)
        self.memory_mbytes = _fetch_and_parse_env_var(ApifyEnvVars.MEMORY_MBYTES)
        self.meta_origin = _fetch_and_parse_env_var(ApifyEnvVars.META_ORIGIN)
        self.metamorph_after_sleep_millis = _fetch_and_parse_env_var(ApifyEnvVars.METAMORPH_AFTER_SLEEP_MILLIS, 300000)
        self.persist_state_interval_millis = _fetch_and_parse_env_var(ApifyEnvVars.PERSIST_STATE_INTERVAL_MILLIS, 60000)
        self.persist_storage = _fetch_and_parse_env_var(ApifyEnvVars.PERSIST_STORAGE)
        self.proxy_hostname = _fetch_and_parse_env_var(ApifyEnvVars.PROXY_HOSTNAME, 'proxy.apify.com')
        self.proxy_password = _fetch_and_parse_env_var(ApifyEnvVars.PROXY_PASSWORD)
        self.proxy_port = _fetch_and_parse_env_var(ApifyEnvVars.PROXY_PORT, 8000)
        self.proxy_status_url = _fetch_and_parse_env_var(ApifyEnvVars.PROXY_STATUS_URL, 'http://proxy.apify.com')
        self.purge_on_start = _fetch_and_parse_env_var(ApifyEnvVars.PURGE_ON_START, True)
        self.started_at = _fetch_and_parse_env_var(ApifyEnvVars.STARTED_AT)
        self.timeout_at = _fetch_and_parse_env_var(ApifyEnvVars.TIMEOUT_AT)
        self.token = _fetch_and_parse_env_var(ApifyEnvVars.TOKEN)
        self.user_id = _fetch_and_parse_env_var(ApifyEnvVars.USER_ID)
        self.xvfb = _fetch_and_parse_env_var(ApifyEnvVars.XVFB, False)

        self.system_info_interval_millis = 60000
        self.max_used_cpu_ratio = 0.95

    @classmethod
    def _get_default_instance(cls) -> 'Configuration':
        if cls._default_instance is None:
            cls._default_instance = cls()

        return cls._default_instance

    @classmethod
    def get_global_configuration(cls) -> 'Configuration':
        """Retrive the global configuration.

        The global configuration applies when you call actor methods via their static versions, e.g. `Actor.init()`.
        Also accessible via `Actor.config`.
        """
        return cls._get_default_instance()
