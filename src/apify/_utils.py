from __future__ import annotations

import builtins
import functools
import sys
from collections import OrderedDict
from collections.abc import MutableMapping
from hashlib import sha256
from importlib import metadata
from logging import getLogger
from typing import Any, Callable, Generic, ItemsView, Iterator, TypeVar, ValuesView, cast
from typing import OrderedDict as OrderedDictType
from urllib.parse import parse_qsl, urlencode, urlparse

from apify_shared.utils import ignore_docs

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
