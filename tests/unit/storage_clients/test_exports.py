from __future__ import annotations

from apify import storage_clients
from apify.storage_clients import ApifyFileSystemStorageClient, FileSystemStorageClient
from apify.storage_clients import _file_system as fs


def test_apify_fs_storage_client_exported_under_real_name() -> None:
    """The Apify FS storage client is importable from `apify.storage_clients` under its real name."""
    assert ApifyFileSystemStorageClient.__name__ == 'ApifyFileSystemStorageClient'
    assert 'ApifyFileSystemStorageClient' in storage_clients.__all__


def test_filesystem_storage_client_alias_kept_for_compat() -> None:
    """The `FileSystemStorageClient` alias stays importable and points at the same class."""
    assert FileSystemStorageClient is ApifyFileSystemStorageClient
    assert 'FileSystemStorageClient' in storage_clients.__all__


def test_file_system_subpackage_exports_all_three_clients() -> None:
    """The `_file_system` sub-package re-exports its dataset, key-value store, and storage clients."""
    assert fs.ApifyFileSystemDatasetClient.__name__ == 'ApifyFileSystemDatasetClient'
    assert fs.ApifyFileSystemKeyValueStoreClient.__name__ == 'ApifyFileSystemKeyValueStoreClient'
    assert fs.ApifyFileSystemStorageClient is ApifyFileSystemStorageClient
