from collections import OrderedDict
from secrets import token_bytes
from typing import Generic, Optional
from typing import OrderedDict as OrderedDictType
from typing import TypeVar, Union

from apify_client import ApifyClientAsync

from ..memory_storage.memory_storage import MemoryStorage


async def _purge_default_storages(client: Union[ApifyClientAsync, MemoryStorage]) -> None:
    if isinstance(client, MemoryStorage) and not client._purged:
        client._purged = True
        await client.purge()


# TODO: would be also possible to replace this with `secrets.token_hex(17)`?
def _crypto_random_object_id(length: int = 17) -> str:
    """Python reimplementation of cryptoRandomObjectId from `@apify/utilities`."""
    chars = 'abcdefghijklmnopqrstuvwxyzABCEDFGHIJKLMNOPQRSTUVWXYZ0123456789'
    chars_len = len(chars)
    # bytes = randbytes(length)
    bytes = token_bytes(length)
    string = ''
    for i in reversed(range(length)):  # TODO: Benchmark performance impact of reverse
        string += chars[(bytes[i] | 0) % chars_len]
    return string


T = TypeVar('T')


class LRUCache(Generic[T]):
    """Attempt to reimplement LRUCache from `@apify/datastructures` using `OrderedDict`."""

    _cache: OrderedDictType[str, T]

    _max_length: int

    def __init__(self, max_length: int) -> None:
        """Crete a LRUCache with a specific max_length."""
        self._cache = OrderedDict()
        self._max_length = max_length

    def get(self, key: str) -> Optional[T]:
        """Get an item from the cache. Move it to the end if present."""
        val = self._cache.get(key)
        if val is not None:
            self._cache.move_to_end(key)
        return val

    def add(self, key: str, value: T) -> bool:
        """Add an item to the cache. Remove least used item if max_length exceeded."""
        if key in self._cache:
            return False
        self._cache[key] = value
        if len(self._cache) > self._max_length:
            self._cache.popitem(last=False)
        return True

    def remove(self, key: str) -> Optional[T]:
        """Remove an item from the cache."""
        return self._cache.pop(key)

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()

    def length(self) -> int:
        """Get the number of items in the cache."""
        return self.__len__()

    def __len__(self) -> int:
        return len(self._cache)
