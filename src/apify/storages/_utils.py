# TODO: randbytes added in 3.9, mypy nicely caught it even though I have 3.10 locally...
# from random import randbytes
from secrets import token_bytes
from typing import Union

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
