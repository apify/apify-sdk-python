import random
import string
from datetime import datetime, timezone
from typing import Any, Dict

import pytest

from apify import Actor
from apify.consts import BOOL_ENV_VARS, DATETIME_ENV_VARS, INTEGER_ENV_VARS, STRING_ENV_VARS, ApifyEnvVars


def print_get_env_var_attr(env_var: str) -> str:
    return env_var.replace('APIFY_', '').lower()


class TestIsAtHome:
    async def test_is_at_home_local(self) -> None:
        async with Actor as actor:
            is_at_home = actor.is_at_home()
            assert is_at_home is False

    async def test_is_at_home_on_apify(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ApifyEnvVars.IS_AT_HOME, 'true')
        async with Actor as actor:
            is_at_home = actor.is_at_home()
            assert is_at_home is True


class TestGetEnv:
    async def test_get_env_use_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Set up random env vars
        expected_get_env: Dict[str, Any] = dict()
        for int_env_var in INTEGER_ENV_VARS:
            int_get_env_var = print_get_env_var_attr(int_env_var)
            expected_get_env[int_get_env_var] = random.randint(1, 99999)
            monkeypatch.setenv(int_env_var, f'{expected_get_env[int_get_env_var]}')

        for bool_env_var in BOOL_ENV_VARS:
            bool_get_env_var = print_get_env_var_attr(bool_env_var)
            expected_get_env[bool_get_env_var] = random.choice([True, False])
            monkeypatch.setenv(bool_env_var, f'{"true" if expected_get_env[bool_get_env_var] else "false"}')

        for datetime_env_var in DATETIME_ENV_VARS:
            datetime_get_env_var = print_get_env_var_attr(datetime_env_var)
            expected_get_env[datetime_get_env_var] = datetime.now().replace(tzinfo=timezone.utc)
            monkeypatch.setenv(datetime_env_var, f'{expected_get_env[datetime_get_env_var].isoformat()}')

        for string_env_var in STRING_ENV_VARS:
            string_get_env_var = print_get_env_var_attr(string_env_var)
            expected_get_env[string_get_env_var] = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            monkeypatch.setenv(string_env_var, expected_get_env[string_get_env_var])

        await Actor.init()
        assert expected_get_env == Actor.get_env()
