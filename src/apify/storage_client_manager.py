from typing import TYPE_CHECKING, Union

from apify_client import ApifyClientAsync

from .memory_storage import MemoryStorage

if TYPE_CHECKING:
    from .config import Configuration


class StorageClientManager:
    """Some logic stolen from Configuration.ts in crawlee, TODO: look for docs there."""

    _config: 'Configuration'

    _client: Union[ApifyClientAsync, MemoryStorage]

    def __init__(self, config: 'Configuration') -> None:
        """TODO: docs."""
        self._config = config
        self._client = self._create_memory_storage()

    def get_storage_client(self) -> Union[ApifyClientAsync, MemoryStorage]:
        """TODO: docs."""
        return self._client

    def _create_memory_storage(self) -> MemoryStorage:
        return MemoryStorage(persist_storage=self._config.persist_storage)

    def set_storage_client(self, client: Union[ApifyClientAsync, MemoryStorage]) -> None:
        """TODO: docs."""
        self._client = client
