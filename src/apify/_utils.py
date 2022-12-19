import asyncio
import errno
import inspect
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar, Union, cast

import psutil
from aiofiles.os import remove
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

# TODO: Compare to https://stackoverflow.com/a/59185523


async def _force_remove(filename: str) -> None:
    """JS-like rm(filename, { force: true })."""
    try:
        await remove(filename)
    except OSError as e:
        if e.errno != errno.ENOENT:  # errno.ENOENT = no such file or directory
            raise  # re-raise exception if a different error occurred


def _json_serializer(obj: Any) -> str:  # TODO: Improve and check this!!!
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
