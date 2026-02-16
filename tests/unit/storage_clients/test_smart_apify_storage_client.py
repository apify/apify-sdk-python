from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apify._configuration import Configuration
from apify.storage_clients import ApifyStorageClient, FileSystemStorageClient
from apify.storage_clients._smart_apify._storage_client import SmartApifyStorageClient


def test_force_cloud_without_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that force_cloud raises RuntimeError when no token is configured."""
    monkeypatch.delenv('APIFY_TOKEN', raising=False)
    monkeypatch.delenv('APIFY_IS_AT_HOME', raising=False)

    client = SmartApifyStorageClient()
    with pytest.raises(RuntimeError, match='you need to provide an Apify token'):
        client.get_suitable_storage_client(force_cloud=True)


def test_force_cloud_with_token_returns_cloud_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that force_cloud returns cloud client when token is available."""
    monkeypatch.setenv('APIFY_TOKEN', 'test-token')
    monkeypatch.delenv('APIFY_IS_AT_HOME', raising=False)

    cloud_client = MagicMock(spec=ApifyStorageClient)
    client = SmartApifyStorageClient(cloud_storage_client=cloud_client)
    result = client.get_suitable_storage_client(force_cloud=True)
    assert result is cloud_client


def test_at_home_returns_cloud_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that at-home always returns cloud client."""
    monkeypatch.setenv('APIFY_IS_AT_HOME', '1')

    cloud_client = MagicMock(spec=ApifyStorageClient)
    client = SmartApifyStorageClient(cloud_storage_client=cloud_client)
    result = client.get_suitable_storage_client()
    assert result is cloud_client


def test_local_returns_local_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that local environment returns local client."""
    monkeypatch.delenv('APIFY_IS_AT_HOME', raising=False)

    local_client = MagicMock(spec=FileSystemStorageClient)
    client = SmartApifyStorageClient(local_storage_client=local_client)
    result = client.get_suitable_storage_client()
    assert result is local_client


def test_default_clients_initialized() -> None:
    """Test that default cloud and local clients are created when not provided."""
    client = SmartApifyStorageClient()
    assert isinstance(client._cloud_storage_client, ApifyStorageClient)
    assert isinstance(client._local_storage_client, FileSystemStorageClient)


def test_str_representation() -> None:
    """Test __str__ returns informative representation."""
    client = SmartApifyStorageClient()
    result = str(client)
    assert 'SmartApifyStorageClient' in result
    assert 'ApifyStorageClient' in result
    assert 'FileSystemStorageClient' in result


def test_cache_key_at_home(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that cache key at home delegates to cloud client."""
    monkeypatch.setenv('APIFY_IS_AT_HOME', '1')
    monkeypatch.setenv('APIFY_TOKEN', 'test-token')

    config = Configuration(is_at_home=True, token='test-token')
    cloud_client = MagicMock(spec=ApifyStorageClient)
    cloud_client.get_storage_client_cache_key.return_value = 'cloud-key'
    client = SmartApifyStorageClient(cloud_storage_client=cloud_client)
    key = client.get_storage_client_cache_key(config)
    assert key == 'cloud-key'
    cloud_client.get_storage_client_cache_key.assert_called_once_with(config)


def test_cache_key_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that cache key locally delegates to local client."""
    monkeypatch.delenv('APIFY_IS_AT_HOME', raising=False)

    config = Configuration()
    local_client = MagicMock(spec=FileSystemStorageClient)
    local_client.get_storage_client_cache_key.return_value = 'local-key'
    client = SmartApifyStorageClient(local_storage_client=local_client)
    key = client.get_storage_client_cache_key(config)
    assert key == 'local-key'
    local_client.get_storage_client_cache_key.assert_called_once_with(config)
