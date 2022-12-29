import asyncio
import datetime
from enum import Enum

import pytest

from apify._utils import (
    _fetch_and_parse_env_var,
    _get_cpu_usage_percent,
    _get_memory_usage_bytes,
    _maybe_extract_enum_member_value,
    _maybe_parse_bool,
    _maybe_parse_datetime,
    _maybe_parse_int,
    _run_func_at_interval_async,
)
from apify.consts import ApifyEnvVars


def test__fetch_and_parse_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ApifyEnvVars.IS_AT_HOME, 'True')
    monkeypatch.setenv(ApifyEnvVars.MEMORY_MBYTES, '1024')
    monkeypatch.setenv(ApifyEnvVars.META_ORIGIN, 'API')
    monkeypatch.setenv(ApifyEnvVars.STARTED_AT, '2022-12-02T15:19:34.907Z')
    monkeypatch.setenv('DUMMY_BOOL', '1')
    monkeypatch.setenv('DUMMY_DATETIME', '2022-12-02T15:19:34.907Z')
    monkeypatch.setenv('DUMMY_INT', '1')
    monkeypatch.setenv('DUMMY_STRING', 'DUMMY')

    assert _fetch_and_parse_env_var(ApifyEnvVars.IS_AT_HOME) is True
    assert _fetch_and_parse_env_var(ApifyEnvVars.MEMORY_MBYTES) == 1024
    assert _fetch_and_parse_env_var(ApifyEnvVars.META_ORIGIN) == 'API'
    assert _fetch_and_parse_env_var(ApifyEnvVars.STARTED_AT) == \
        datetime.datetime(2022, 12, 2, 15, 19, 34, 907000, tzinfo=datetime.timezone.utc)

    assert _fetch_and_parse_env_var('DUMMY_BOOL') == '1'  # type: ignore
    assert _fetch_and_parse_env_var('DUMMY_DATETIME') == '2022-12-02T15:19:34.907Z'  # type: ignore
    assert _fetch_and_parse_env_var('DUMMY_INT') == '1'  # type: ignore
    assert _fetch_and_parse_env_var('DUMMY_STRING') == 'DUMMY'  # type: ignore
    assert _fetch_and_parse_env_var('NONEXISTENT_ENV_VAR') is None  # type: ignore
    assert _fetch_and_parse_env_var('NONEXISTENT_ENV_VAR', 'default') == 'default'  # type: ignore


def test__get_cpu_usage_percent() -> None:
    assert _get_cpu_usage_percent() >= 0
    assert _get_cpu_usage_percent() <= 100


def test__get_memory_usage_bytes() -> None:
    assert _get_memory_usage_bytes() >= 0
    assert _get_memory_usage_bytes() <= 1024 * 1024 * 1024 * 1024


def test__maybe_extract_enum_member_value() -> None:
    class TestEnum(Enum):
        A = 'A'
        B = 'B'

    assert _maybe_extract_enum_member_value(TestEnum.A) == 'A'
    assert _maybe_extract_enum_member_value(TestEnum.B) == 'B'
    assert _maybe_extract_enum_member_value('C') == 'C'
    assert _maybe_extract_enum_member_value(1) == 1
    assert _maybe_extract_enum_member_value(None) is None


def test__maybe_parse_bool() -> None:
    assert _maybe_parse_bool('True') is True
    assert _maybe_parse_bool('true') is True
    assert _maybe_parse_bool('1') is True
    assert _maybe_parse_bool('False') is False
    assert _maybe_parse_bool('false') is False
    assert _maybe_parse_bool('0') is False
    assert _maybe_parse_bool(None) is False
    assert _maybe_parse_bool('bflmpsvz') is False


def test__maybe_parse_datetime() -> None:
    assert _maybe_parse_datetime('2022-12-02T15:19:34.907Z') == \
        datetime.datetime(2022, 12, 2, 15, 19, 34, 907000, tzinfo=datetime.timezone.utc)
    assert _maybe_parse_datetime('2022-12-02T15:19:34.907') == '2022-12-02T15:19:34.907'
    assert _maybe_parse_datetime('anything') == 'anything'


def test__maybe_parse_int() -> None:
    assert _maybe_parse_int('0') == 0
    assert _maybe_parse_int('1') == 1
    assert _maybe_parse_int('-1') == -1
    assert _maybe_parse_int('136749825') == 136749825
    assert _maybe_parse_int('') is None
    assert _maybe_parse_int('abcd') is None


@pytest.mark.asyncio
async def test__run_func_at_interval_async() -> None:
    # Test that it works with a synchronous functions
    test_var = 0

    def sync_increment() -> None:
        nonlocal test_var
        test_var += 1

    sync_increment_task = asyncio.create_task(_run_func_at_interval_async(sync_increment, 0.3))

    await asyncio.sleep(0.2)
    assert test_var == 0
    await asyncio.sleep(0.3)
    assert test_var == 1
    await asyncio.sleep(0.3)
    assert test_var == 2
    await asyncio.sleep(0.3)
    assert test_var == 3

    sync_increment_task.cancel()

    await asyncio.sleep(1)
    assert test_var == 3

    # Test that it works with an asynchronous functions
    test_var = 0

    async def async_increment() -> None:
        nonlocal test_var
        await asyncio.sleep(0.1)
        test_var += 1

    async_increment_task = asyncio.create_task(_run_func_at_interval_async(async_increment, 0.3))

    await asyncio.sleep(0.2)
    assert test_var == 0
    await asyncio.sleep(0.3)
    assert test_var == 1
    await asyncio.sleep(0.3)
    assert test_var == 2
    await asyncio.sleep(0.3)
    assert test_var == 3

    async_increment_task.cancel()

    await asyncio.sleep(1)
    assert test_var == 3
