import asyncio
import contextlib
import inspect
import json
import os
import sys
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar, Union, cast, overload

import psutil
from aiofiles.os import remove

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


class ListPage:
    """A single page of items returned from a list() method."""

    #: list: List of returned objects on this page
    items: List
    #: int: Count of the returned objects on this page
    count: int
    #: int: The limit on the number of returned objects offset specified in the API call
    offset: int
    #: int: The offset of the first object specified in the API call
    limit: int
    #: int: Total number of objects matching the API call criteria
    total: int
    #: bool: Whether the listing is descending or not
    desc: bool

    def __init__(self, data: Dict) -> None:
        """Initialize a ListPage instance from the API response data."""
        self.items = data['items'] if 'items' in data else []
        self.offset = data['offset'] if 'offset' in data else 0
        self.limit = data['limit'] if 'limit' in data else 0
        self.count = data['count'] if 'count' in data else len(self.items)
        self.total = data['total'] if 'total' in data else self.offset + self.count
        self.desc = data['desc'] if 'desc' in data else False


async def _force_remove(filename: str) -> None:
    """JS-like rm(filename, { force: true })."""
    with contextlib.suppress(FileNotFoundError):
        await remove(filename)


def _json_serializer(obj: Any) -> str:  # TODO: Decide how to parse/dump/handle datetimes!
    if isinstance(obj, (datetime)):
        return obj.isoformat(timespec='milliseconds') + 'Z'
    else:
        return str(obj)


def _filter_out_none_values_recursively(dictionary: Dict) -> Dict:
    """Return copy of the dictionary, recursively omitting all keys for which values are None."""
    return cast(dict, _filter_out_none_values_recursively_internal(dictionary))


# Unfortunately, it's necessary to have an internal function for the correct result typing, without having to create complicated overloads
def _filter_out_none_values_recursively_internal(dictionary: Dict, remove_empty_dicts: Optional[bool] = None) -> Optional[Dict]:
    result = {}
    for k, v in dictionary.items():
        if isinstance(v, dict):
            v = _filter_out_none_values_recursively_internal(v, remove_empty_dicts is True or remove_empty_dicts is None)
        if v is not None:
            result[k] = v
    if not result and remove_empty_dicts:
        return None
    return result


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=_json_serializer)
