import asyncio
import inspect
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Callable, Generic, Optional, TypeVar, Union, cast

import psutil
from apify_client import __version__ as client_version

from ._version import __version__ as sdk_version
from .consts import BOOL_ENV_VARS, DATETIME_ENV_VARS, INTEGER_ENV_VARS


def _log_system_info() -> None:
    python_version = '.'.join([str(x) for x in sys.version_info[:3]])

    print('System info:')
    print(f'    Apify SDK version: {sdk_version}')
    print(f'    Apify Client version: {client_version}')
    print(f'    OS: {sys.platform}')
    print(f'    Python version: {python_version}')


ClassPropertyType = TypeVar('ClassPropertyType')


class classproperty(Generic[ClassPropertyType]):  # noqa: N801
    """TODO: no docs."""

    def __init__(self, getter: Callable[..., ClassPropertyType]) -> None:
        """TODO: no docs."""
        self.getter = getter

    def __get__(self, _: Any, owner: Any) -> ClassPropertyType:  # noqa: U101
        """TODO: no docs."""
        return self.getter(owner)


def _fetch_and_parse_env_var(env_var_name: str, default: Any = None) -> Any:
    val = os.getenv(env_var_name)
    if not val:
        return default

    if env_var_name in BOOL_ENV_VARS:
        return _maybe_parse_bool(val)
    if env_var_name in INTEGER_ENV_VARS:
        return _maybe_parse_int(val)
    if env_var_name in DATETIME_ENV_VARS:
        return _maybe_parse_datetime(val)
    return val


def _get_cpu_usage_percent() -> float:
    return psutil.cpu_percent()


def _get_memory_usage_bytes() -> int:
    current_process = psutil.Process(os.getpid())
    mem = cast(int, current_process.memory_info().rss or 0)
    for child in current_process.children(recursive=True):
        try:
            mem += cast(int, child.memory_info().rss or 0)
        except psutil.NoSuchProcess:
            pass
    return mem


def _maybe_parse_bool(val: Optional[str]) -> bool:
    if val == 'true' or val == 'True' or val == '1':
        return True
    return False


def _maybe_parse_datetime(val: Optional[str]) -> Union[Optional[datetime], Optional[str]]:
    if not val:
        return None
    try:
        return datetime.strptime(val, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc)
    except ValueError:
        return val


def _maybe_parse_int(val: Optional[str]) -> Optional[int]:
    if not val:
        return None
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
