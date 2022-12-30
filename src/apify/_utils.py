import asyncio
import inspect
import os
import sys
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Generic, Optional, TypeVar, Union, overload

import psutil

from apify_client import __version__ as client_version

from ._version import __version__ as sdk_version
from .consts import (
    _BOOL_ENV_VARS_TYPE,
    _DATETIME_ENV_VARS_TYPE,
    _INTEGER_ENV_VARS_TYPE,
    _STRING_ENV_VARS_TYPE,
    BOOL_ENV_VARS,
    DATETIME_ENV_VARS,
    INTEGER_ENV_VARS,
    ApifyEnvVars,
)


def _log_system_info() -> None:
    python_version = '.'.join([str(x) for x in sys.version_info[:3]])

    print('System info:')
    print(f'    Apify SDK version: {sdk_version}')
    print(f'    Apify Client version: {client_version}')
    print(f'    OS: {sys.platform}')
    print(f'    Python version: {python_version}')


DualPropertyType = TypeVar('DualPropertyType')


class dualproperty(Generic[DualPropertyType]):  # noqa: N801
    """TODO: no docs."""

    def __init__(self, getter: Callable[..., DualPropertyType]) -> None:
        """TODO: no docs."""
        self.getter = getter

    def __get__(self, obj: Any, owner: Any) -> DualPropertyType:
        """TODO: no docs."""
        return self.getter(obj or owner)


def _maybe_extract_enum_member_value(maybe_enum_member: Any) -> Any:
    if isinstance(maybe_enum_member, Enum):
        return maybe_enum_member.value
    return maybe_enum_member


@overload
def _fetch_and_parse_env_var(env_var: _BOOL_ENV_VARS_TYPE) -> Optional[bool]:  # noqa: U100
    ...


@overload
def _fetch_and_parse_env_var(env_var: _BOOL_ENV_VARS_TYPE, default: bool) -> bool:  # noqa: U100
    ...


@overload
def _fetch_and_parse_env_var(env_var: _DATETIME_ENV_VARS_TYPE) -> Optional[Union[datetime, str]]:  # noqa: U100
    ...


@overload
def _fetch_and_parse_env_var(env_var: _DATETIME_ENV_VARS_TYPE, default: datetime) -> Union[datetime, str]:  # noqa: U100
    ...


@overload
def _fetch_and_parse_env_var(env_var: _INTEGER_ENV_VARS_TYPE) -> Optional[int]:  # noqa: U100
    ...


@overload
def _fetch_and_parse_env_var(env_var: _INTEGER_ENV_VARS_TYPE, default: int) -> int:  # noqa: U100
    ...


@overload
def _fetch_and_parse_env_var(env_var: _STRING_ENV_VARS_TYPE, default: str) -> str:  # noqa: U100
    ...


@overload
def _fetch_and_parse_env_var(env_var: _STRING_ENV_VARS_TYPE) -> Optional[str]:  # noqa: U100
    ...


@overload
def _fetch_and_parse_env_var(env_var: ApifyEnvVars) -> Optional[Any]:  # noqa: U100
    ...


def _fetch_and_parse_env_var(env_var: Any, default: Any = None) -> Any:
    env_var_name = str(_maybe_extract_enum_member_value(env_var))

    val = os.getenv(env_var_name)
    if not val:
        return default

    if env_var in BOOL_ENV_VARS:
        return _maybe_parse_bool(val)
    if env_var in INTEGER_ENV_VARS:
        res = _maybe_parse_int(val)
        if res is None:
            return default
        return res
    if env_var in DATETIME_ENV_VARS:
        return _maybe_parse_datetime(val)
    return val


def _get_cpu_usage_percent() -> float:
    return psutil.cpu_percent()


def _get_memory_usage_bytes() -> int:
    current_process = psutil.Process(os.getpid())
    mem = int(current_process.memory_info().rss or 0)
    for child in current_process.children(recursive=True):
        try:
            mem += int(child.memory_info().rss or 0)
        except psutil.NoSuchProcess:
            pass
    return mem


def _maybe_parse_bool(val: Optional[str]) -> bool:
    if val == 'true' or val == 'True' or val == '1':
        return True
    return False


def _maybe_parse_datetime(val: str) -> Union[datetime, str]:
    try:
        return datetime.strptime(val, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc)
    except ValueError:
        return val


def _maybe_parse_int(val: str) -> Optional[int]:
    try:
        return int(val)
    except ValueError:
        return None


async def _run_func_at_interval_async(func: Callable, interval_secs: float) -> None:
    try:
        started_at = time.time()
        while True:
            elapsed_secs = time.time() - started_at
            sleep_for_secs = interval_secs - (elapsed_secs % interval_secs)
            await asyncio.sleep(sleep_for_secs)

            res = func()
            if inspect.isawaitable(res):
                await res
    except asyncio.CancelledError:
        pass
