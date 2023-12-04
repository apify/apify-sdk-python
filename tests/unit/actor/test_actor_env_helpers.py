from __future__ import annotations

import random
import string
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from apify import Actor
from apify_shared.consts import BOOL_ENV_VARS, DATETIME_ENV_VARS, FLOAT_ENV_VARS, INTEGER_ENV_VARS, STRING_ENV_VARS, ActorEnvVars, ApifyEnvVars

if TYPE_CHECKING:
    import pytest


class TestIsAtHome:
    async def test_is_at_home_local(self: TestIsAtHome) -> None:
        async with Actor as actor:
            is_at_home = actor.is_at_home()
            assert is_at_home is False

    async def test_is_at_home_on_apify(self: TestIsAtHome, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ApifyEnvVars.IS_AT_HOME, 'true')
        async with Actor as actor:
            is_at_home = actor.is_at_home()
            assert is_at_home is True


class TestGetEnv:
    async def test_get_env_use_env_vars(self: TestGetEnv, monkeypatch: pytest.MonkeyPatch) -> None:
        # Set up random env vars
        expected_get_env: dict[str, Any] = {}
        for int_env_var in INTEGER_ENV_VARS:
            int_get_env_var = int_env_var.name.lower()
            expected_get_env[int_get_env_var] = random.randint(1, 99999)
            monkeypatch.setenv(int_env_var, f'{expected_get_env[int_get_env_var]}')

        for float_env_var in FLOAT_ENV_VARS:
            float_get_env_var = float_env_var.name.lower()
            expected_get_env[float_get_env_var] = random.random()
            monkeypatch.setenv(float_env_var, f'{expected_get_env[float_get_env_var]}')

        for bool_env_var in BOOL_ENV_VARS:
            bool_get_env_var = bool_env_var.name.lower()
            expected_get_env[bool_get_env_var] = random.choice([True, False])
            monkeypatch.setenv(bool_env_var, f'{"true" if expected_get_env[bool_get_env_var] else "false"}')

        for datetime_env_var in DATETIME_ENV_VARS:
            datetime_get_env_var = datetime_env_var.name.lower()
            expected_get_env[datetime_get_env_var] = datetime.now(timezone.utc)
            monkeypatch.setenv(datetime_env_var, expected_get_env[datetime_get_env_var].strftime('%Y-%m-%dT%H:%M:%S.%fZ'))

        for string_env_var in STRING_ENV_VARS:
            string_get_env_var = string_env_var.name.lower()
            expected_get_env[string_get_env_var] = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            monkeypatch.setenv(string_env_var, expected_get_env[string_get_env_var])

        # We need this override so that the actor doesn't fail when connecting to the platform events websocket
        monkeypatch.delenv(ActorEnvVars.EVENTS_WEBSOCKET_URL)
        expected_get_env[ActorEnvVars.EVENTS_WEBSOCKET_URL.name.lower()] = None

        await Actor.init()
        assert expected_get_env == Actor.get_env()

        await Actor.exit()
