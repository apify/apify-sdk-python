from datetime import datetime
from typing import Optional, cast

from ._utils import _fetch_and_parse_env_var


class Configuration:
    """TODO: docs."""

    def __init__(self) -> None:
        """TODO: docs."""
        self.actor_build_id = cast(Optional[str], _fetch_and_parse_env_var('APIFY_ACTOR_BUILD_ID'))
        self.actor_build_number = cast(Optional[str], _fetch_and_parse_env_var('APIFY_ACTOR_BUILD_NUMBER'))
        self.actor_events_ws_url = cast(Optional[str], _fetch_and_parse_env_var('APIFY_ACTOR_EVENTS_WS_URL'))
        self.actor_id = cast(Optional[str], _fetch_and_parse_env_var('APIFY_ACTOR_ID'))
        self.actor_run_id = cast(Optional[str], _fetch_and_parse_env_var('APIFY_ACTOR_RUN_ID'))
        self.actor_task_id = cast(Optional[str], _fetch_and_parse_env_var('APIFY_ACTOR_TASK_ID'))
        self.api_base_url = cast(str, _fetch_and_parse_env_var('APIFY_API_BASE_URL', 'https://api.apify.com'))
        self.api_public_base_url = cast(str, _fetch_and_parse_env_var('APIFY_API_PUBLIC_BASE_URL', 'https://api.apify.com'))
        self.chrome_executable_path = cast(Optional[str], _fetch_and_parse_env_var('APIFY_CHROME_EXECUTABLE_PATH'))
        self.container_port = cast(str, _fetch_and_parse_env_var('APIFY_CONTAINER_PORT', 4321))
        self.container_url = cast(str, _fetch_and_parse_env_var('APIFY_CONTAINER_URL', 'http://localhost:4321'))
        self.dedicated_cpus = cast(Optional[str], _fetch_and_parse_env_var('APIFY_DEDICATED_CPUS'))
        self.default_browser_path = cast(Optional[str], _fetch_and_parse_env_var('APIFY_DEFAULT_BROWSER_PATH'))
        self.default_dataset_id = cast(str, _fetch_and_parse_env_var('APIFY_DEFAULT_DATASET_ID', 'default'))
        self.default_key_value_store_id = cast(str, _fetch_and_parse_env_var('APIFY_DEFAULT_KEY_VALUE_STORE_ID', 'default'))
        self.default_request_queue_id = cast(str, _fetch_and_parse_env_var('APIFY_DEFAULT_REQUEST_QUEUE_ID', 'default'))
        self.disable_browser_sandbox = cast(Optional[str], _fetch_and_parse_env_var('APIFY_DISABLE_BROWSER_SANDBOX'))
        self.headless = cast(bool, _fetch_and_parse_env_var('APIFY_HEADLESS', True))
        self.input_key = cast(str, _fetch_and_parse_env_var('APIFY_INPUT_KEY', 'INPUT'))
        self.input_secrets_private_key_file = cast(Optional[str], _fetch_and_parse_env_var('APIFY_INPUT_SECRETS_PRIVATE_KEY_FILE'))
        self.input_secrets_private_key_passphrase = cast(Optional[str], _fetch_and_parse_env_var('APIFY_INPUT_SECRETS_PRIVATE_KEY_PASSPHRASE'))
        self.is_at_home = cast(bool, _fetch_and_parse_env_var('APIFY_IS_AT_HOME', False))
        self.memory_mbytes = cast(Optional[str], _fetch_and_parse_env_var('APIFY_MEMORY_MBYTES'))
        self.meta_origin = cast(Optional[str], _fetch_and_parse_env_var('APIFY_META_ORIGIN'))
        self.metamorph_after_sleep_millis = cast(int, _fetch_and_parse_env_var('APIFY_METAMORPH_AFTER_SLEEP_MILLIS', 300000))
        self.persist_state_interval_millis = cast(int, _fetch_and_parse_env_var('APIFY_PERSIST_STATE_INTERVAL_MILLIS', 60000))
        self.proxy_hostname = cast(str, _fetch_and_parse_env_var('APIFY_PROXY_HOSTNAME', 'proxy.apify.com'))
        self.proxy_password = cast(Optional[str], _fetch_and_parse_env_var('APIFY_PROXY_PASSWORD'))
        self.proxy_port = cast(int, _fetch_and_parse_env_var('APIFY_PROXY_PORT', 8000))
        self.proxy_status_url = cast(str, _fetch_and_parse_env_var('APIFY_PROXY_STATUS_URL', 'http://proxy.apify.com'))
        self.purge_on_start = cast(bool, _fetch_and_parse_env_var('APIFY_PURGE_ON_START', True))
        self.started_at = cast(Optional[datetime], _fetch_and_parse_env_var('APIFY_STARTED_AT'))
        self.timeout_at = cast(Optional[datetime], _fetch_and_parse_env_var('APIFY_TIMEOUT_AT'))
        self.token = cast(Optional[str], _fetch_and_parse_env_var('APIFY_TOKEN'))
        self.user_id = cast(Optional[str], _fetch_and_parse_env_var('APIFY_USER_ID'))
        self.xvfb = cast(bool, _fetch_and_parse_env_var('APIFY_XVFB', False))

        self.system_info_interval_millis = 60000
        self.max_used_cpu_ratio = 0.95
