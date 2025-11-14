from __future__ import annotations

import random
import string
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from pydantic_core import TzInfo

from apify_shared.consts import (
    BOOL_ENV_VARS,
    COMMA_SEPARATED_LIST_ENV_VARS,
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


async def test_actor_is_not_at_home_when_local() -> None:
    async with Actor as actor:
        is_at_home = actor.is_at_home()
        assert is_at_home is False


async def test_get_env_with_randomized_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    ignored_env_vars = {
        ApifyEnvVars.SDK_LATEST_VERSION,
        ApifyEnvVars.LOG_FORMAT,
        ApifyEnvVars.LOG_LEVEL,
        ActorEnvVars.STANDBY_PORT,
        ApifyEnvVars.PERSIST_STORAGE,
    }

    # Set up random env vars
    expected_get_env = dict[str, Any]()
    expected_get_env[ApifyEnvVars.LOG_LEVEL.name.lower()] = 'INFO'

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
        if float_env_var == ActorEnvVars.MAX_TOTAL_CHARGE_USD:
            expected_get_env[float_get_env_var] = Decimal(random.random())
        else:
            expected_get_env[float_get_env_var] = random.random()
        monkeypatch.setenv(float_env_var, f'{expected_get_env[float_get_env_var]}')

    for bool_env_var in BOOL_ENV_VARS:
        if bool_env_var in ignored_env_vars:
            continue

        bool_get_env_var = bool_env_var.name.lower()
        expected_get_env[bool_get_env_var] = random.choice([True, False])
        monkeypatch.setenv(bool_env_var, f'{"true" if expected_get_env[bool_get_env_var] else "false"}')

    expected_get_env[ApifyEnvVars.IS_AT_HOME.name.lower()] = False
    monkeypatch.setenv(ApifyEnvVars.IS_AT_HOME, 'false')

    for datetime_env_var in DATETIME_ENV_VARS:
        if datetime_env_var in ignored_env_vars:
            continue

        datetime_get_env_var = datetime_env_var.name.lower()
        expected_get_env[datetime_get_env_var] = datetime.now(TzInfo(0))
        monkeypatch.setenv(
            datetime_env_var,
            expected_get_env[datetime_get_env_var].strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
        )

    for string_env_var in STRING_ENV_VARS:
        if string_env_var in ignored_env_vars:
            continue

        string_get_env_var = string_env_var.name.lower()
        expected_value = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        # URLs have to be valid
        if string_get_env_var.endswith('url'):
            expected_value = f'http://example.com/{expected_value}'
        expected_get_env[string_get_env_var] = expected_value
        monkeypatch.setenv(string_env_var, expected_get_env[string_get_env_var])

    for list_env_var in COMMA_SEPARATED_LIST_ENV_VARS:
        if list_env_var in ignored_env_vars:
            continue

        available_values = ['val1', 'val2']

        list_get_env_var = list_env_var.name.lower()
        expected_value_count = random.randint(0, len(available_values))
        expected_get_env[list_get_env_var] = random.sample(available_values, expected_value_count)
        monkeypatch.setenv(list_env_var, ','.join(expected_get_env[list_get_env_var]))

        # Test behavior with missing env var in case of empty list
        if expected_value_count == 0 and random.random() < 0.5:
            monkeypatch.delenv(list_env_var)
            expected_get_env[list_get_env_var] = None

    # We need this override so that the actor doesn't fail when connecting to the platform events websocket
    monkeypatch.delenv(ActorEnvVars.EVENTS_WEBSOCKET_URL)
    expected_get_env[ActorEnvVars.EVENTS_WEBSOCKET_URL.name.lower()] = None

    # Adjust expectations for timedelta fields
    for env_name, env_value in expected_get_env.items():
        if env_name.endswith('_millis'):
            expected_get_env[env_name] = timedelta(milliseconds=env_value)

    # Convert dedicated_cpus to float
    expected_get_env[ApifyEnvVars.DEDICATED_CPUS.name.lower()] = float(
        expected_get_env[ApifyEnvVars.DEDICATED_CPUS.name.lower()]
    )

    await Actor.init()
    assert Actor.get_env() == expected_get_env

    await Actor.exit()
