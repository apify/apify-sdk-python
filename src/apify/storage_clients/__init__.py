# `FileSystemStorageClient`, `MemoryStorageClient`, and `StorageClient` are re-exported unchanged from Crawlee.
# The file-system client also has an Apify variant, `ApifyFileSystemStorageClient` (the default local client),
# which preserves the Actor `INPUT` record on purge and charges for the `PAY_PER_EVENT` pricing model. There is
# no Apify variant of `MemoryStorageClient`, so it is re-exported as-is and provides neither behavior. Prefer
# the Apify clients when either behavior matters.
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
