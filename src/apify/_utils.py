from __future__ import annotations

import asyncio
import base64
import builtins
import contextlib
import functools
import hashlib
import inspect
import json
import mimetypes
import os
import re
import sys
import time
from collections import OrderedDict
from collections.abc import MutableMapping
from datetime import datetime, timezone
from importlib import metadata
from typing import (
    Any,
    Callable,
    Generic,
    ItemsView,
    Iterator,
    NoReturn,
    TypeVar,
    ValuesView,
    cast,
    overload,
)
from typing import OrderedDict as OrderedDictType

import aioshutil
import psutil
from aiofiles import ospath
from aiofiles.os import remove, rename

from apify_shared.consts import (
    BOOL_ENV_VARS,
    BOOL_ENV_VARS_TYPE,
    DATETIME_ENV_VARS,
    DATETIME_ENV_VARS_TYPE,
    FLOAT_ENV_VARS,
    FLOAT_ENV_VARS_TYPE,
    INTEGER_ENV_VARS,
    INTEGER_ENV_VARS_TYPE,
    STRING_ENV_VARS_TYPE,
    ActorEnvVars,
    ApifyEnvVars,
)
from apify_shared.utils import (
    ignore_docs,
    is_content_type_json,
    is_content_type_text,
    is_content_type_xml,
    maybe_extract_enum_member_value,
)

from .consts import REQUEST_ID_LENGTH, StorageTypes

T = TypeVar('T')


def get_system_info() -> dict:
    python_version = '.'.join([str(x) for x in sys.version_info[:3]])

    system_info: dict[str, str | bool] = {
        'apify_sdk_version': metadata.version('apify'),
        'apify_client_version': metadata.version('apify-client'),
        'python_version': python_version,
        'os': sys.platform,
    }

    if is_running_in_ipython():
        system_info['is_running_in_ipython'] = True

    return system_info


DualPropertyType = TypeVar('DualPropertyType')
DualPropertyOwner = TypeVar('DualPropertyOwner')


@ignore_docs
class dualproperty(Generic[DualPropertyType]):  # noqa: N801
    """Descriptor combining `property` and `classproperty`.

    When accessing the decorated attribute on an instance, it calls the getter with the instance as the first argument,
    and when accessing it on a class, it calls the getter with the class as the first argument.
    """

    def __init__(self: dualproperty, getter: Callable[..., DualPropertyType]) -> None:
        """Initialize the dualproperty.

        Args:
            getter (Callable): The getter of the property.
            It should accept either an instance or a class as its first argument.
        """
        self.getter = getter

    def __get__(self: dualproperty, obj: DualPropertyOwner | None, owner: type[DualPropertyOwner]) -> DualPropertyType:
        """Call the getter with the right object.

        Args:
            obj (T | None): The instance of class T on which the getter will be called
            owner (type[T]): The class object of class T on which the getter will be called, if obj is None

        Returns:
            The result of the getter.
        """
        val = self.getter(obj or owner)
        return cast(DualPropertyType, val)


@overload
def fetch_and_parse_env_var(env_var: BOOL_ENV_VARS_TYPE) -> bool | None:
    ...


@overload
def fetch_and_parse_env_var(env_var: BOOL_ENV_VARS_TYPE, default: bool) -> bool:  # noqa: FBT001
    ...


@overload
def fetch_and_parse_env_var(env_var: DATETIME_ENV_VARS_TYPE) -> datetime | str | None:
    ...


@overload
def fetch_and_parse_env_var(env_var: DATETIME_ENV_VARS_TYPE, default: datetime) -> datetime | str:
    ...


@overload
def fetch_and_parse_env_var(env_var: FLOAT_ENV_VARS_TYPE) -> float | None:
    ...


@overload
def fetch_and_parse_env_var(env_var: FLOAT_ENV_VARS_TYPE, default: float) -> float:
    ...


@overload
def fetch_and_parse_env_var(env_var: INTEGER_ENV_VARS_TYPE) -> int | None:
    ...


@overload
def fetch_and_parse_env_var(env_var: INTEGER_ENV_VARS_TYPE, default: int) -> int:
    ...


@overload
def fetch_and_parse_env_var(env_var: STRING_ENV_VARS_TYPE, default: str) -> str:
    ...


@overload
def fetch_and_parse_env_var(env_var: STRING_ENV_VARS_TYPE) -> str | None:
    ...


@overload
def fetch_and_parse_env_var(env_var: ActorEnvVars | ApifyEnvVars) -> Any:
    ...


def fetch_and_parse_env_var(env_var: Any, default: Any = None) -> Any:
    env_var_name = str(maybe_extract_enum_member_value(env_var))

    val = os.getenv(env_var_name)
    if not val:
        return default

    if env_var in BOOL_ENV_VARS:
        return maybe_parse_bool(val)
    if env_var in FLOAT_ENV_VARS:
        parsed_float = maybe_parse_float(val)
        if parsed_float is None:
            return default
        return parsed_float
    if env_var in INTEGER_ENV_VARS:
        parsed_int = maybe_parse_int(val)
        if parsed_int is None:
            return default
        return parsed_int
    if env_var in DATETIME_ENV_VARS:
        return maybe_parse_datetime(val)
    return val


def get_cpu_usage_percent() -> float:
    return psutil.cpu_percent()


def get_memory_usage_bytes() -> int:
    current_process = psutil.Process(os.getpid())
    mem = int(current_process.memory_info().rss or 0)
    for child in current_process.children(recursive=True):
        with contextlib.suppress(psutil.NoSuchProcess):
            mem += int(child.memory_info().rss or 0)
    return mem


def maybe_parse_bool(val: str | None) -> bool:
    if val in {'true', 'True', '1'}:
        return True
    return False


def maybe_parse_datetime(val: str) -> datetime | str:
    try:
        return datetime.strptime(val, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc)
    except ValueError:
        return val


def maybe_parse_float(val: str) -> float | None:
    try:
        return float(val)
    except ValueError:
        return None


def maybe_parse_int(val: str) -> int | None:
    try:
        return int(val)
    except ValueError:
        return None


async def run_func_at_interval_async(func: Callable, interval_secs: float) -> None:
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


async def force_remove(filename: str) -> None:
    """JS-like rm(filename, { force: true })."""
    with contextlib.suppress(FileNotFoundError):
        await remove(filename)


def raise_on_non_existing_storage(client_type: StorageTypes, id: str) -> NoReturn:  # noqa: A002
    client_type = maybe_extract_enum_member_value(client_type)
    raise ValueError(f'{client_type} with id "{id}" does not exist.')


def raise_on_duplicate_storage(client_type: StorageTypes, key_name: str, value: str) -> NoReturn:
    client_type = maybe_extract_enum_member_value(client_type)
    raise ValueError(f'{client_type} with {key_name} "{value}" already exists.')


def guess_file_extension(content_type: str) -> str | None:
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


def maybe_parse_body(body: bytes, content_type: str) -> Any:
    if is_content_type_json(content_type):
        return json.loads(body.decode('utf-8'))  # Returns any
    if is_content_type_xml(content_type) or is_content_type_text(content_type):
        return body.decode('utf-8')
    return body


def unique_key_to_request_id(unique_key: str) -> str:
    """Generate request ID based on unique key in a deterministic way."""
    id = re.sub(r'(\+|\/|=)', '', base64.b64encode(hashlib.sha256(unique_key.encode('utf-8')).digest()).decode('utf-8'))  # noqa: A001

    return id[:REQUEST_ID_LENGTH] if len(id) > REQUEST_ID_LENGTH else id


async def force_rename(src_dir: str, dst_dir: str) -> None:
    """Rename a directory. Checks for existence of soruce directory and removes destination directory if it exists."""
    # Make sure source directory exists
    if await ospath.exists(src_dir):
        # Remove destination directory if it exists
        if await ospath.exists(dst_dir):
            await aioshutil.rmtree(dst_dir, ignore_errors=True)
        await rename(src_dir, dst_dir)


ImplementationType = TypeVar('ImplementationType', bound=Callable)
MetadataType = TypeVar('MetadataType', bound=Callable)


def wrap_internal(implementation: ImplementationType, metadata_source: MetadataType) -> MetadataType:
    @functools.wraps(metadata_source)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return implementation(*args, **kwargs)

    return cast(MetadataType, wrapper)


@ignore_docs
class LRUCache(MutableMapping, Generic[T]):
    """Attempt to reimplement LRUCache from `@apify/datastructures` using `OrderedDict`."""

    _cache: OrderedDictType[str, T]

    _max_length: int

    def __init__(self: LRUCache, max_length: int) -> None:
        """Create a LRUCache with a specific max_length."""
        self._cache = OrderedDict()
        self._max_length = max_length

    def __getitem__(self: LRUCache, key: str) -> T:
        """Get an item from the cache. Move it to the end if present."""
        val = self._cache[key]
        # No 'key in cache' condition since the previous line would raise KeyError
        self._cache.move_to_end(key)
        return cast(T, val)

    # Sadly TS impl returns bool indicating whether the key was already present or not
    def __setitem__(self: LRUCache, key: str, value: T) -> None:
        """Add an item to the cache. Remove least used item if max_length exceeded."""
        self._cache[key] = value
        if len(self._cache) > self._max_length:
            self._cache.popitem(last=False)

    def __delitem__(self: LRUCache, key: str) -> None:
        """Remove an item from the cache."""
        del self._cache[key]

    def __iter__(self: LRUCache) -> Iterator[str]:
        """Iterate over the keys of the cache in order of insertion."""
        return self._cache.__iter__()

    def __len__(self: LRUCache) -> int:
        """Get the number of items in the cache."""
        return len(self._cache)

    def values(self: LRUCache) -> ValuesView[T]:  # Needed so we don't mutate the cache by __getitem__
        """Iterate over the values in the cache in order of insertion."""
        return self._cache.values()

    def items(self: LRUCache) -> ItemsView[str, T]:  # Needed so we don't mutate the cache by __getitem__
        """Iterate over the pairs of (key, value) in the cache in order of insertion."""
        return self._cache.items()


def is_running_in_ipython() -> bool:
    return getattr(builtins, '__IPYTHON__', False)


@overload
def budget_ow(value: str | float | bool, predicate: tuple[type, bool], value_name: str) -> None:
    ...


@overload
def budget_ow(value: dict, predicate: dict[str, tuple[type, bool]]) -> None:
    ...


def budget_ow(
    value: dict | str | float | bool,
    predicate: dict[str, tuple[type, bool]] | tuple[type, bool],
    value_name: str | None = None,
) -> None:
    """Budget version of ow."""

    def validate_single(field_value: Any, expected_type: type, required: bool, name: str) -> None:  # noqa: FBT001
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


PARSE_DATE_FIELDS_MAX_DEPTH = 3
PARSE_DATE_FIELDS_KEY_SUFFIX = 'At'
ListOrDictOrAny = TypeVar('ListOrDictOrAny', list, dict, Any)
