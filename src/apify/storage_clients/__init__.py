# `FileSystemStorageClient`, `MemoryStorageClient`, and `StorageClient` are re-exported from Crawlee. Only the
# file-system client has an Apify variant: `ApifyFileSystemStorageClient`, the default local client, which adds
# `INPUT` preservation on purge and local `PAY_PER_EVENT` charging.
from crawlee.storage_clients import FileSystemStorageClient, MemoryStorageClient, StorageClient

from ._apify import ApifyStorageClient
from ._file_system import ApifyFileSystemStorageClient
from ._smart_apify import SmartApifyStorageClient

__all__ = [
    'ApifyFileSystemStorageClient',
    'ApifyStorageClient',
    'FileSystemStorageClient',
    'MemoryStorageClient',
    'SmartApifyStorageClient',
    'StorageClient',
]
