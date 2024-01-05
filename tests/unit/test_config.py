from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from apify_shared.consts import ActorEnvVars, ApifyEnvVars

from apify.config import Configuration

if TYPE_CHECKING:
    import pytest


class TestConfiguration:
    # Test that some config properties have some reasonable defaults
    def test_configuration_defaults(self: TestConfiguration) -> None:
        config = Configuration()
        assert config.token is None
        assert config.proxy_password is None
        assert config.api_base_url == 'https://api.apify.com'
        assert config.proxy_hostname == 'proxy.apify.com'
        assert config.default_dataset_id == 'default'
        assert config.default_key_value_store_id == 'default'
        assert config.default_request_queue_id == 'default'
        assert config.is_at_home is False
        assert config.proxy_port == 8000
        assert config.memory_mbytes is None
        assert config.started_at is None

    # Test that defining properties via env vars works
    def test_configuration_from_env_vars(self: TestConfiguration, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ApifyEnvVars.TOKEN, 'DUMMY_TOKEN')
        monkeypatch.setenv(ApifyEnvVars.PROXY_PASSWORD, 'DUMMY_PROXY_PASSWORD')
        monkeypatch.setenv(ApifyEnvVars.API_BASE_URL, 'DUMMY_API_BASE_URL')
        monkeypatch.setenv(ApifyEnvVars.PROXY_HOSTNAME, 'DUMMY_PROXY_HOSTNAME')
        monkeypatch.setenv(ActorEnvVars.DEFAULT_KEY_VALUE_STORE_ID, 'DUMMY_DEFAULT_KEY_VALUE_STORE_ID')
        monkeypatch.setenv(ActorEnvVars.DEFAULT_REQUEST_QUEUE_ID, 'DUMMY_DEFAULT_REQUEST_QUEUE_ID')
        monkeypatch.setenv(ActorEnvVars.DEFAULT_DATASET_ID, 'DUMMY_DEFAULT_DATASET_ID')
        monkeypatch.setenv(ApifyEnvVars.IS_AT_HOME, '1')
        monkeypatch.setenv(ApifyEnvVars.PROXY_PORT, '1234')
        monkeypatch.setenv(ActorEnvVars.MEMORY_MBYTES, '1024')
        monkeypatch.setenv(ActorEnvVars.STARTED_AT, '2023-01-01T12:34:56.789Z')

        config = Configuration()
        assert config.token == 'DUMMY_TOKEN'
        assert config.proxy_password == 'DUMMY_PROXY_PASSWORD'
        assert config.api_base_url == 'DUMMY_API_BASE_URL'
        assert config.proxy_hostname == 'DUMMY_PROXY_HOSTNAME'
        assert config.default_dataset_id == 'DUMMY_DEFAULT_DATASET_ID'
        assert config.default_key_value_store_id == 'DUMMY_DEFAULT_KEY_VALUE_STORE_ID'
        assert config.default_request_queue_id == 'DUMMY_DEFAULT_REQUEST_QUEUE_ID'
        assert config.is_at_home is True
        assert config.proxy_port == 1234
        assert config.memory_mbytes == 1024
        assert config.started_at == datetime(2023, 1, 1, 12, 34, 56, 789000, tzinfo=timezone.utc)

    # Test that constructor arguments take precedence over env vars
    def test_configuration_from_constructor_arguments(self: TestConfiguration, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ApifyEnvVars.TOKEN, 'DUMMY_TOKEN')
        monkeypatch.setenv(ApifyEnvVars.PROXY_PASSWORD, 'DUMMY_PROXY_PASSWORD')
        monkeypatch.setenv(ApifyEnvVars.API_BASE_URL, 'DUMMY_API_BASE_URL')
        monkeypatch.setenv(ApifyEnvVars.PROXY_HOSTNAME, 'DUMMY_PROXY_HOSTNAME')
        monkeypatch.setenv(ActorEnvVars.DEFAULT_DATASET_ID, 'DUMMY_DEFAULT_DATASET_ID')
        monkeypatch.setenv(ActorEnvVars.DEFAULT_KEY_VALUE_STORE_ID, 'DUMMY_DEFAULT_KEY_VALUE_STORE_ID')
        monkeypatch.setenv(ActorEnvVars.DEFAULT_REQUEST_QUEUE_ID, 'DUMMY_DEFAULT_REQUEST_QUEUE_ID')
        monkeypatch.setenv(ApifyEnvVars.PROXY_PORT, '1234')

        config = Configuration(
            token='TOKEN_FROM_CONSTRUCTOR',
            proxy_password='PROXY_PASSWORD_FROM_CONSTRUCTOR',
            proxy_hostname='PROXY_HOSTNAME_FROM_CONSTRUCTOR',
            api_base_url='API_BASE_URL_FROM_CONSTRUCTOR',
            default_dataset_id='DEFAULT_DATASET_ID_FROM_CONSTRUCTOR',
            default_key_value_store_id='DEFAULT_KEY_VALUE_STORE_ID_FROM_CONSTRUCTOR',
            default_request_queue_id='DEFAULT_REQUEST_QUEUE_ID_FROM_CONSTRUCTOR',
            proxy_port=5678,
        )

        assert config.token == 'TOKEN_FROM_CONSTRUCTOR'
        assert config.proxy_password == 'PROXY_PASSWORD_FROM_CONSTRUCTOR'
        assert config.api_base_url == 'API_BASE_URL_FROM_CONSTRUCTOR'
        assert config.proxy_hostname == 'PROXY_HOSTNAME_FROM_CONSTRUCTOR'
        assert config.default_dataset_id == 'DEFAULT_DATASET_ID_FROM_CONSTRUCTOR'
        assert config.default_key_value_store_id == 'DEFAULT_KEY_VALUE_STORE_ID_FROM_CONSTRUCTOR'
        assert config.default_request_queue_id == 'DEFAULT_REQUEST_QUEUE_ID_FROM_CONSTRUCTOR'
        assert config.proxy_port == 5678
