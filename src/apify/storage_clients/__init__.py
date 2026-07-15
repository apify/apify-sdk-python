# `MemoryStorageClient` is re-exported from Crawlee unchanged. Unlike `ApifyFileSystemStorageClient`, it does
# not preserve the Actor `INPUT` record on purge, and unlike the Apify dataset clients it does not charge for
# the `PAY_PER_EVENT` pricing model, so prefer the Apify clients when either behavior matters.
from crawlee.storage_clients import MemoryStorageClient, StorageClient

from ._apify import ApifyStorageClient
from ._file_system import ApifyFileSystemStorageClient
from ._smart_apify import SmartApifyStorageClient

__all__ = [
    'ApifyFileSystemStorageClient',
    'ApifyStorageClient',
    'MemoryStorageClient',
    'SmartApifyStorageClient',
    'StorageClient',
]
