from __future__ import annotations

import asyncio
import builtins
import contextlib
import functools
import inspect
import json
import mimetypes
import os
import re
import sys
import time
from base64 import b64encode
from collections import OrderedDict
from collections.abc import MutableMapping
from datetime import datetime, timezone
from hashlib import sha256
from importlib import metadata
from logging import getLogger
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
from urllib.parse import parse_qsl, urlencode, urlparse

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

from apify.consts import REQUEST_ID_LENGTH, StorageTypes

T = TypeVar('T')
logger = getLogger(__name__)


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
    request_id = re.sub(r'(\+|\/|=)', '', b64encode(sha256(unique_key.encode('utf-8')).digest()).decode('utf-8'))
    return request_id[:REQUEST_ID_LENGTH] if len(request_id) > REQUEST_ID_LENGTH else request_id


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


def compute_short_hash(data: bytes, *, length: int = 8) -> str:
    """Computes a hexadecimal SHA-256 hash of the provided data and returns a substring (prefix) of it.

    Args:
        data: The binary data to be hashed.
        length: The length of the hash to be returned.

    Returns:
        A substring (prefix) of the hexadecimal hash of the data.
    """
    hash_object = sha256(data)
    return hash_object.hexdigest()[:length]


def normalize_url(url: str, *, keep_url_fragment: bool = False) -> str:
    """Normalizes a URL.

    This function cleans and standardizes a URL by removing leading and trailing whitespaces,
    converting the scheme and netloc to lower case, stripping unwanted tracking parameters
    (specifically those beginning with 'utm_'), sorting the remaining query parameters alphabetically,
    and optionally retaining the URL fragment. The goal is to ensure that URLs that are functionally
    identical but differ in trivial ways (such as parameter order or casing) are treated as the same.

    Args:
        url: The URL to be normalized.
        keep_url_fragment: Flag to determine whether the fragment part of the URL should be retained.

    Returns:
        A string containing the normalized URL.
    """
    # Parse the URL
    parsed_url = urlparse(url.strip())
    search_params = dict(parse_qsl(parsed_url.query))  # Convert query to a dict

    # Remove any 'utm_' parameters
    search_params = {k: v for k, v in search_params.items() if not k.startswith('utm_')}

    # Construct the new query string
    sorted_keys = sorted(search_params.keys())
    sorted_query = urlencode([(k, search_params[k]) for k in sorted_keys])

    # Construct the final URL
    new_url = (
        parsed_url._replace(
            query=sorted_query,
            scheme=parsed_url.scheme,
            netloc=parsed_url.netloc,
            path=parsed_url.path.rstrip('/'),
        )
        .geturl()
        .lower()
    )

    # Retain the URL fragment if required
    if not keep_url_fragment:
        new_url = new_url.split('#')[0]

    return new_url


def compute_unique_key(
    url: str,
    method: str = 'GET',
    payload: bytes | None = None,
    *,
    keep_url_fragment: bool = False,
    use_extended_unique_key: bool = False,
) -> str:
    """Computes a unique key for caching & deduplication of requests.

    This function computes a unique key by normalizing the provided URL and method.
    If 'use_extended_unique_key' is True and a payload is provided, the payload is hashed and
    included in the key. Otherwise, the unique key is just the normalized URL.

    Args:
        url: The request URL.
        method: The HTTP method, defaults to 'GET'.
        payload: The request payload, defaults to None.
        keep_url_fragment: A flag indicating whether to keep the URL fragment, defaults to False.
        use_extended_unique_key: A flag indicating whether to include a hashed payload in the key, defaults to False.

    Returns:
        A string representing the unique key for the request.
    """
    # Normalize the URL and method.
    try:
        normalized_url = normalize_url(url, keep_url_fragment=keep_url_fragment)
    except Exception as exc:
        logger.warning(f'Failed to normalize URL: {exc}')
        normalized_url = url

    normalized_method = method.upper()

    # Compute and return the extended unique key if required.
    if use_extended_unique_key:
        payload_hash = compute_short_hash(payload) if payload else ''
        return f'{normalized_method}({payload_hash}):{normalized_url}'

    # Log information if there is a non-GET request with a payload.
    if normalized_method != 'GET' and payload:
        logger.info(
            f'We have encountered a {normalized_method} Request with a payload. This is fine. Just letting you know '
            'that if your requests point to the same URL and differ only in method and payload, you should consider '
            'using the "use_extended_unique_key" option.'
        )

    # Return the normalized URL as the unique key.
    return normalized_url
