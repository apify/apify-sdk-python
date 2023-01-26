from typing import Optional, Union

from apify_client import ApifyClientAsync

from .config import Configuration
from .memory_storage import MemoryStorage


class StorageClientManager:
    """A class for managing storage clients."""

    _config: Configuration

    _client: Union[ApifyClientAsync, MemoryStorage]

    _default_instance: Optional['StorageClientManager'] = None

    def __init__(self) -> None:
        """Create a `StorageClientManager` instance."""
        self._config = Configuration.get_global_configuration()
        self._client = MemoryStorage(persist_storage=self._config.persist_storage)

    @classmethod
    def get_storage_client(cls) -> Union[ApifyClientAsync, MemoryStorage]:
        """Get the current storage client instance.

        Returns:
            ApifyClientAsync or MemoryStorage: The current storage client instance.
        """
        return cls._get_default_instance()._client

    @classmethod
    def set_storage_client(cls, client: Union[ApifyClientAsync, MemoryStorage]) -> None:
        """Set the storage client.

        Args:
            client (ApifyClientAsync or MemoryStorage): The instance of a storage client.
        """
        cls._get_default_instance()._client = client

    @classmethod
    def _get_default_instance(cls) -> 'StorageClientManager':
        if cls._default_instance is None:
            cls._default_instance = cls()

        return cls._default_instance
