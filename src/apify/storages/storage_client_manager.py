from typing import Optional, Union

from apify_client import ApifyClientAsync

from ..config import Configuration
from ..memory_storage import MemoryStorage


class StorageClientManager:
    """A class for managing storage clients."""

    _config: Configuration

    _local_client: Optional[MemoryStorage] = None
    _cloud_client: Optional[ApifyClientAsync] = None

    _default_instance: Optional['StorageClientManager'] = None

    def __init__(self) -> None:
        """Create a `StorageClientManager` instance."""
        self._config = Configuration.get_global_configuration()

    @classmethod
    def set_config(cls, config: Configuration) -> None:
        """Set the config for the StorageClientManager.

        Args:
            config (Configuration): The configuration this StorageClientManager should use.
        """
        cls._get_default_instance()._config = config

    @classmethod
    def get_storage_client(cls, force_cloud: bool = False) -> Union[ApifyClientAsync, MemoryStorage]:
        """Get the current storage client instance.

        Returns:
            ApifyClientAsync or MemoryStorage: The current storage client instance.
        """
        default_instance = cls._get_default_instance()
        if not default_instance._local_client:
            default_instance._local_client = MemoryStorage(persist_storage=default_instance._config.persist_storage, write_metadata=True)

        if default_instance._config.is_at_home or force_cloud:
            assert default_instance._cloud_client is not None
            return default_instance._cloud_client

        return default_instance._local_client

    @classmethod
    def set_cloud_client(cls, client: ApifyClientAsync) -> None:
        """Set the storage client.

        Args:
            client (ApifyClientAsync or MemoryStorage): The instance of a storage client.
        """
        cls._get_default_instance()._cloud_client = client

    @classmethod
    def _get_default_instance(cls) -> 'StorageClientManager':
        if cls._default_instance is None:
            cls._default_instance = cls()

        return cls._default_instance
