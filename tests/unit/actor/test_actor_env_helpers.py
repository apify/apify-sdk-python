from __future__ import annotations

import random
import string
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from pydantic_core import TzInfo

from apify_shared.consts import (
    BOOL_ENV_VARS,
    DATETIME_ENV_VARS,
    FLOAT_ENV_VARS,
    INTEGER_ENV_VARS,
    STRING_ENV_VARS,
    ActorEnvVars,
    ApifyEnvVars,
)

from apify import Actor

if TYPE_CHECKING:
    import pytest


class TestIsAtHome:
    async def test_is_at_home_local(self) -> None:
        async with Actor as actor:
            is_at_home = actor.is_at_home()
            assert is_at_home is False

    async def test_is_at_home_on_apify(self, monkeypatch: pytest.MonkeyPatch) -> None:
        print('setenv')
        monkeypatch.setenv(ApifyEnvVars.IS_AT_HOME, 'true')
        async with Actor as actor:
            is_at_home = actor.is_at_home()
            assert is_at_home is True


class TestGetEnv:
    async def test_get_env_use_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ignored_env_vars = {
            ApifyEnvVars.INPUT_KEY,
            ApifyEnvVars.MEMORY_MBYTES,
            ApifyEnvVars.STARTED_AT,
            ApifyEnvVars.TIMEOUT_AT,
            ApifyEnvVars.DEFAULT_DATASET_ID,
            ApifyEnvVars.DEFAULT_KEY_VALUE_STORE_ID,
            ApifyEnvVars.DEFAULT_REQUEST_QUEUE_ID,
            ApifyEnvVars.SDK_LATEST_VERSION,
            ApifyEnvVars.LOG_FORMAT,
        }

        legacy_env_vars = {
            ApifyEnvVars.ACT_ID: ActorEnvVars.ID,
            ApifyEnvVars.ACT_RUN_ID: ActorEnvVars.RUN_ID,
            ApifyEnvVars.ACTOR_ID: ActorEnvVars.ID,
            ApifyEnvVars.ACTOR_BUILD_ID: ActorEnvVars.BUILD_ID,
            ApifyEnvVars.ACTOR_BUILD_NUMBER: ActorEnvVars.BUILD_NUMBER,
            ApifyEnvVars.ACTOR_RUN_ID: ActorEnvVars.RUN_ID,
            ApifyEnvVars.ACTOR_TASK_ID: ActorEnvVars.TASK_ID,
            ApifyEnvVars.CONTAINER_URL: ActorEnvVars.WEB_SERVER_URL,
            ApifyEnvVars.CONTAINER_PORT: ActorEnvVars.WEB_SERVER_PORT,
        }

        # Set up random env vars
        expected_get_env: dict[str, Any] = {}
        for int_env_var in INTEGER_ENV_VARS:
            if int_env_var in ignored_env_vars:
                continue

            int_get_env_var = int_env_var.name.lower()
            expected_get_env[int_get_env_var] = random.randint(1, 99999)
            monkeypatch.setenv(int_env_var, f'{expected_get_env[int_get_env_var]}')

        for float_env_var in FLOAT_ENV_VARS:
            if float_env_var in ignored_env_vars:
                continue

            float_get_env_var = float_env_var.name.lower()
            expected_get_env[float_get_env_var] = random.random()
            monkeypatch.setenv(float_env_var, f'{expected_get_env[float_get_env_var]}')

        for bool_env_var in BOOL_ENV_VARS:
            if bool_env_var in ignored_env_vars:
                continue

            bool_get_env_var = bool_env_var.name.lower()
            expected_get_env[bool_get_env_var] = random.choice([True, False])
            monkeypatch.setenv(bool_env_var, f'{"true" if expected_get_env[bool_get_env_var] else "false"}')

        for datetime_env_var in DATETIME_ENV_VARS:
            if datetime_env_var in ignored_env_vars:
                continue

            datetime_get_env_var = datetime_env_var.name.lower()
            expected_get_env[datetime_get_env_var] = datetime.now(TzInfo(0))  # type: ignore
            monkeypatch.setenv(
                datetime_env_var,
                expected_get_env[datetime_get_env_var].strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            )

        for string_env_var in STRING_ENV_VARS:
            if string_env_var in ignored_env_vars:
                continue

            string_get_env_var = string_env_var.name.lower()
            expected_get_env[string_get_env_var] = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            monkeypatch.setenv(string_env_var, expected_get_env[string_get_env_var])

        # We need this override so that the actor doesn't fail when connecting to the platform events websocket
        monkeypatch.delenv(ActorEnvVars.EVENTS_WEBSOCKET_URL)
        monkeypatch.delenv(ApifyEnvVars.ACTOR_EVENTS_WS_URL)
        expected_get_env[ActorEnvVars.EVENTS_WEBSOCKET_URL.name.lower()] = None
        expected_get_env[ApifyEnvVars.ACTOR_EVENTS_WS_URL.name.lower()] = None

        # Adjust expectations for timedelta fields
        for env_name, env_value in expected_get_env.items():
            if env_name.endswith('_millis'):
                expected_get_env[env_name] = timedelta(milliseconds=env_value)

        # Convert dedicated_cpus to float
        expected_get_env[ApifyEnvVars.DEDICATED_CPUS.name.lower()] = float(
            expected_get_env[ApifyEnvVars.DEDICATED_CPUS.name.lower()]
        )

        # Update expectations for legacy configuration
        for old_name, new_name in legacy_env_vars.items():
            expected_get_env[old_name.name.lower()] = expected_get_env[new_name.name.lower()]

        await Actor.init()
        assert Actor.get_env() == expected_get_env

        await Actor.exit()
