import asyncio
import base64
import builtins
import contextlib
import functools
import hashlib
import inspect
import io
import json
import mimetypes
import os
import re
import sys
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, Generic, NoReturn, Optional, Type, TypeVar, Union, cast, overload

import aioshutil
import psutil
from aiofiles import ospath
from aiofiles.os import remove, rename

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
    REQUEST_ID_LENGTH,
    ApifyEnvVars,
    StorageTypes,
)


def _log_system_info() -> None:
    python_version = '.'.join([str(x) for x in sys.version_info[:3]])

    print('System info:')
    print(f'    Apify SDK version: {sdk_version}')
    print(f'    Apify Client version: {client_version}')
    print(f'    OS: {sys.platform}')
    print(f'    Python version: {python_version}')
    if _is_running_in_ipython():
        print('    Running in IPython: True')


DualPropertyType = TypeVar('DualPropertyType')
DualPropertyOwner = TypeVar('DualPropertyOwner')


class dualproperty(Generic[DualPropertyType]):  # noqa: N801
    """Descriptor combining `property` and `classproperty`.

    When accessing the decorated attribute on an instance, it calls the getter with the instance as the first argument,
    and when accessing it on a class, it calls the getter with the class as the first argument.
    """

    def __init__(self, getter: Callable[..., DualPropertyType]) -> None:
        """Initialize the dualproperty.

        Args:
            getter (Callable): The getter of the property.
            It should accept either an instance or a class as its first argument.
        """
        self.getter = getter

    def __get__(self, obj: Optional[DualPropertyOwner], owner: Type[DualPropertyOwner]) -> DualPropertyType:
        """Call the getter with the right object.

        Args:
            obj (Optional[T]): The instance of class T on which the getter will be called
            owner (Type[T]): The class object of class T on which the getter will be called, if obj is None

        Returns:
            The result of the getter.
        """
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
    started_at = time.time()
    while True:
        elapsed_secs = time.time() - started_at
        sleep_for_secs = interval_secs - (elapsed_secs % interval_secs)
        await asyncio.sleep(sleep_for_secs)

        res = func()
        if inspect.isawaitable(res):
            await res


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
    """Dump JSON to a string with the correct settings and serializer."""
    return json.dumps(obj, ensure_ascii=False, indent=2, default=_json_serializer)


uuid_regex = re.compile('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)


def _is_uuid(string: str) -> bool:
    """Test whether the given string matches UUID format."""
    return bool(uuid_regex.match(string))


def _raise_on_non_existing_storage(client_type: StorageTypes, id: str) -> NoReturn:
    raise ValueError(f'{client_type} with id: {id} does not exist.')


def _raise_on_duplicate_storage(client_type: StorageTypes, key_name: str, value: str) -> NoReturn:
    raise ValueError(f'{client_type} with {key_name}: {value} already exists.')


def _guess_file_extension(content_type: str) -> Optional[str]:
    """Guess the file extension based on content type."""
    # e.g. mimetypes.guess_extension('application/json ') does not work...
    actual_content_type = content_type.split(';')[0].strip()
    ext = mimetypes.guess_extension(actual_content_type)
    # Remove the leading dot if extension successfully parsed
    return ext[1:] if ext is not None else ext


def _is_content_type_json(content_type: str) -> bool:
    return bool(re.search(r'^application/json', content_type, flags=re.IGNORECASE))


def _is_content_type_xml(content_type: str) -> bool:
    return bool(re.search(r'^application/.*xml$', content_type, flags=re.IGNORECASE))


def _is_content_type_text(content_type: str) -> bool:
    return bool(re.search(r'^text/', content_type, flags=re.IGNORECASE))


def _is_file_or_bytes(value: Any) -> bool:
    # The check for IOBase is not ideal, it would be better to use duck typing,
    # but then the check would be super complex, judging from how the 'requests' library does it.
    # This way should be good enough for the vast majority of use cases, if it causes issues, we can improve it later.
    return isinstance(value, (bytes, bytearray, io.IOBase))


def _maybe_parse_body(body: bytes, content_type: str) -> Any:  # TODO: Improve return type
    try:
        if _is_content_type_json(content_type):
            return json.loads(body)  # Returns any
        elif _is_content_type_xml(content_type) or _is_content_type_text(content_type):
            return body.decode('utf-8')  # TODO: Check if utf-8 can be assumed
    except ValueError as err:
        print('_maybe_parse_body error', err)
    return body


def _unique_key_to_request_id(unique_key: str) -> str:
    """Generate request ID based on unique key in a deterministic way."""
    id = re.sub(r'(\+|\/|=)', '', base64.b64encode(hashlib.sha256(unique_key.encode('utf-8')).digest()).decode('utf-8'))

    return id[:REQUEST_ID_LENGTH] if len(id) > REQUEST_ID_LENGTH else id


async def _force_rename(src_dir: str, dst_dir: str) -> None:
    """Rename a directory. Checks for existence of soruce directory and removes destination directory if it exists."""
    # Make sure source directory exists
    if await ospath.exists(src_dir):
        # Remove destination directory if it exists
        if await ospath.exists(dst_dir):
            await aioshutil.rmtree(dst_dir, ignore_errors=True)
        await rename(src_dir, dst_dir)

ImplementationType = TypeVar('ImplementationType', bound=Callable)
MetadataType = TypeVar('MetadataType', bound=Callable)


def _wrap_internal(implementation: ImplementationType, metadata_source: MetadataType) -> MetadataType:
    @functools.wraps(metadata_source)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return implementation(*args, **kwargs)

    return cast(MetadataType, wrapper)


def _is_running_in_ipython() -> bool:
    return getattr(builtins, '__IPYTHON__', False)
