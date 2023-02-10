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
from collections import OrderedDict
from collections.abc import MutableMapping
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, Generic, ItemsView, Iterator, NoReturn, Optional
from typing import OrderedDict as OrderedDictType
from typing import Tuple, Type, TypeVar, Union, ValuesView, cast, overload

import aioshutil
import psutil
from aiofiles import ospath
from aiofiles.os import remove, rename

from apify_client import __version__ as client_version

from ._version import __version__ as sdk_version
from .consts import (
    _BOOL_ENV_VARS_TYPE,
    _DATETIME_ENV_VARS_TYPE,
    _FLOAT_ENV_VARS_TYPE,
    _INTEGER_ENV_VARS_TYPE,
    _STRING_ENV_VARS_TYPE,
    BOOL_ENV_VARS,
    DATETIME_ENV_VARS,
    FLOAT_ENV_VARS,
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
def _fetch_and_parse_env_var(env_var: _BOOL_ENV_VARS_TYPE) -> Optional[bool]:
    ...


@overload
def _fetch_and_parse_env_var(env_var: _BOOL_ENV_VARS_TYPE, default: bool) -> bool:
    ...


@overload
def _fetch_and_parse_env_var(env_var: _DATETIME_ENV_VARS_TYPE) -> Optional[Union[datetime, str]]:
    ...


@overload
def _fetch_and_parse_env_var(env_var: _DATETIME_ENV_VARS_TYPE, default: datetime) -> Union[datetime, str]:
    ...


@overload
def _fetch_and_parse_env_var(env_var: _FLOAT_ENV_VARS_TYPE) -> Optional[float]:
    ...


@overload
def _fetch_and_parse_env_var(env_var: _FLOAT_ENV_VARS_TYPE, default: float) -> float:
    ...


@overload
def _fetch_and_parse_env_var(env_var: _INTEGER_ENV_VARS_TYPE) -> Optional[int]:
    ...


@overload
def _fetch_and_parse_env_var(env_var: _INTEGER_ENV_VARS_TYPE, default: int) -> int:
    ...


@overload
def _fetch_and_parse_env_var(env_var: _STRING_ENV_VARS_TYPE, default: str) -> str:
    ...


@overload
def _fetch_and_parse_env_var(env_var: _STRING_ENV_VARS_TYPE) -> Optional[str]:
    ...


@overload
def _fetch_and_parse_env_var(env_var: ApifyEnvVars) -> Optional[Any]:
    ...


def _fetch_and_parse_env_var(env_var: Any, default: Any = None) -> Any:
    env_var_name = str(_maybe_extract_enum_member_value(env_var))

    val = os.getenv(env_var_name)
    if not val:
        return default

    if env_var in BOOL_ENV_VARS:
        return _maybe_parse_bool(val)
    if env_var in FLOAT_ENV_VARS:
        parsed_float = _maybe_parse_float(val)
        if parsed_float is None:
            return default
        return parsed_float
    if env_var in INTEGER_ENV_VARS:
        parsed_int = _maybe_parse_int(val)
        if parsed_int is None:
            return default
        return parsed_int
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


def _maybe_parse_float(val: str) -> Optional[float]:
    try:
        return float(val)
    except ValueError:
        return None


def _maybe_parse_int(val: str) -> Optional[int]:
    try:
        return int(val)
    except ValueError:
        return None


async def _run_func_at_interval_async(func: Callable, interval_secs: float) -> None:
    started_at = time.perf_counter()
    sleep_until = started_at
    while True:
        now = time.perf_counter()
        sleep_until += interval_secs
        while sleep_until < now:
            sleep_until += interval_secs

        sleep_for_secs = sleep_until - now
        await asyncio.sleep(sleep_for_secs)

        res = func()
        if inspect.isawaitable(res):
            await res


async def _force_remove(filename: str) -> None:
    """JS-like rm(filename, { force: true })."""
    with contextlib.suppress(FileNotFoundError):
        await remove(filename)


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
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


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

    # mimetypes.guess_extension returns 'xsl' in this case, because 'application/xxx' is "structured"
    # ('text/xml' would be "unstructured" and return 'xml')
    # we have to explicitly override it here
    if actual_content_type == 'application/xml':
        return 'xml'

    # Guess the extension from the mime type
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


def _maybe_parse_body(body: bytes, content_type: str) -> Any:
    try:
        if _is_content_type_json(content_type):
            return json.loads(body)  # Returns any
        elif _is_content_type_xml(content_type) or _is_content_type_text(content_type):
            return body.decode('utf-8')
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


T = TypeVar('T')


class LRUCache(MutableMapping, Generic[T]):
    """Attempt to reimplement LRUCache from `@apify/datastructures` using `OrderedDict`."""

    _cache: OrderedDictType[str, T]

    _max_length: int

    def __init__(self, max_length: int) -> None:
        """Create a LRUCache with a specific max_length."""
        self._cache = OrderedDict()
        self._max_length = max_length

    def __getitem__(self, key: str) -> T:
        """Get an item from the cache. Move it to the end if present."""
        val = self._cache[key]
        # No 'key in cache' condition since the previous line would raise KeyError
        self._cache.move_to_end(key)
        return val

    # Sadly TS impl returns bool indicating whether the key was already present or not
    def __setitem__(self, key: str, value: T) -> None:
        """Add an item to the cache. Remove least used item if max_length exceeded."""
        self._cache[key] = value
        if len(self._cache) > self._max_length:
            self._cache.popitem(last=False)

    def __delitem__(self, key: str) -> None:
        """Remove an item from the cache."""
        del self._cache[key]

    def __iter__(self) -> Iterator[str]:
        """Iterate over the keys of the cache in order of insertion."""
        return self._cache.__iter__()

    def __len__(self) -> int:
        """Get the number of items in the cache."""
        return len(self._cache)

    def values(self) -> ValuesView[T]:  # Needed so we don't mutate the cache by __getitem__
        """Iterate over the values in the cache in order of insertion."""
        return self._cache.values()

    def items(self) -> ItemsView[str, T]:  # Needed so we don't mutate the cache by __getitem__
        """Iterate over the pairs of (key, value) in the cache in order of insertion."""
        return self._cache.items()


def _is_running_in_ipython() -> bool:
    return getattr(builtins, '__IPYTHON__', False)


@overload
def _budget_ow(value: Union[str, int, float, bool], predicate: Tuple[Type, bool], value_name: str) -> None:
    ...


@overload
def _budget_ow(value: Dict, predicate: Dict[str, Tuple[Type, bool]]) -> None:
    ...


def _budget_ow(
    value: Union[Dict, str, int, float, bool],
    predicate: Union[Dict[str, Tuple[Type, bool]], Tuple[Type, bool]],
    value_name: Optional[str] = None,
) -> None:
    """Budget version of ow."""
    def validate_single(field_value: Any, expected_type: Type, required: bool, name: str) -> None:
        if field_value is None and required:
            raise ValueError(f'"{name}" is required!')
        if (field_value is not None or required) and not isinstance(field_value, expected_type):
            raise ValueError(f'"{name}" must be of type "{expected_type.__name__}" but it is "{type(field_value).__name__}"!')

    # Validate object
    if isinstance(value, dict) and isinstance(predicate, dict):
        for key, (field_type, required) in predicate.items():
            field_value = value.get(key)
            validate_single(field_value, field_type, required, key)
    # Validate "primitive"
    elif isinstance(value, (int, str, float, bool)) and isinstance(predicate, tuple) and value_name is not None:
        field_type, required = predicate
        validate_single(value, field_type, required, value_name)
    else:
        raise ValueError('Wrong input!')
