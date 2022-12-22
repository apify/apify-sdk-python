import os
from pathlib import Path
from typing import List, Optional

import aioshutil
from aiofiles import ospath
from aiofiles.os import rename, scandir

from .resource_clients.dataset import DatasetClient
from .resource_clients.dataset_collection import DatasetCollectionClient
from .resource_clients.key_value_store import KeyValueStoreClient
from .resource_clients.key_value_store_collection import KeyValueStoreCollectionClient
from .resource_clients.request_queue import RequestQueueClient
from .resource_clients.request_queue_collection import RequestQueueCollectionClient


class MemoryStorage:
    """Class representing an in-memory storage."""

    datasets_handled: List[DatasetClient] = []
    key_value_stores_handled: List[KeyValueStoreClient] = []
    request_queues_handled: List[RequestQueueClient] = []

    def __init__(
        self, *, local_data_directory: str = './storage', write_metadata: Optional[bool] = False, persist_storage: Optional[bool] = True,
    ) -> None:
        """TODO: docs."""
        self.local_data_directory = local_data_directory
        self.datasets_directory = os.path.join(self.local_data_directory, 'datasets')
        self.key_value_stores_directory = os.path.join(self.local_data_directory, 'key_value_stores')
        self.request_queues_directory = os.path.join(self.local_data_directory, 'request_queues')
        self.write_metadata = write_metadata or '*' in os.getenv('DEBUG', '')
        self.persist_storage = persist_storage or not any(s in os.getenv('APIFY_PERSIST_STORAGE', 'true') for s in ['false', '0', ''])

    def datasets(self) -> DatasetCollectionClient:
        """TODO: docs."""
        return DatasetCollectionClient(base_storage_directory=self.datasets_directory, client=self)

    def dataset(self, *, id: str) -> DatasetClient:
        """TODO: docs."""
        return DatasetClient(base_storage_directory=self.datasets_directory, client=self, id=id)

    def key_value_stores(self) -> KeyValueStoreCollectionClient:
        """TODO: docs."""
        return KeyValueStoreCollectionClient(base_storage_directory=self.key_value_stores_directory, client=self)

    def key_value_store(self, *, id: str) -> KeyValueStoreClient:
        """TODO: docs."""
        return KeyValueStoreClient(base_storage_directory=self.key_value_stores_directory, client=self, id=id)

    def request_queues(self) -> RequestQueueCollectionClient:
        """TODO: docs."""
        return RequestQueueCollectionClient(base_storage_directory=self.request_queues_directory, client=self)

    def request_queue(self, *, id: str, client_key: Optional[str] = None, timeout_secs: Optional[int] = None) -> RequestQueueClient:
        """TODO: docs."""
        return RequestQueueClient(base_storage_directory=self.request_queues_directory, client=self, id=id)

    async def purge(self) -> None:
        """TODO: docs."""
        # Key-value stores
        if await ospath.exists(self.key_value_stores_directory):
            key_value_store_folders = await scandir(self.key_value_stores_directory)
            for key_value_store_folder in key_value_store_folders:
                if key_value_store_folder.name.startswith('__APIFY_TEMPORARY') or key_value_store_folder.name.startswith('__OLD'):
                    await self._batch_remove_files(os.path.join(self.key_value_stores_directory, key_value_store_folder.name))
                elif key_value_store_folder.name == 'default':
                    await self._handle_default_key_value_store(os.path.join(self.key_value_stores_directory, key_value_store_folder.name))

        # Datasets
        if await ospath.exists(self.datasets_directory):
            dataset_folders = await scandir(self.datasets_directory)
            for dataset_folder in dataset_folders:
                if dataset_folder.name == 'default' or dataset_folder.name.startswith('__APIFY_TEMPORARY'):
                    print(dataset_folder.name)
                    await self._batch_remove_files(os.path.join(self.datasets_directory, dataset_folder.name))
        # Request queues
        if await ospath.exists(self.request_queues_directory):
            request_queue_folders = await scandir(self.request_queues_directory)
            for request_queue_folder in request_queue_folders:
                if request_queue_folder.name == 'default' or request_queue_folder.name.startswith('__APIFY_TEMPORARY'):
                    await self._batch_remove_files(os.path.join(self.request_queues_directory, request_queue_folder.name))

    def teardown(self) -> None:
        """TODO: docs."""
        # We don't need to wait for anything here since we don't have worker threads for fs operations
        pass

    async def _handle_default_key_value_store(self, folder: str) -> None:
        folder_exists = await ospath.exists(folder)
        temporary_path = os.path.join(folder, '../__APIFY_MIGRATING_KEY_VALUE_STORE__')

        # For optimization, we want to only attempt to copy a few files from the default key-value store
        possible_input_keys = [
            'INPUT',
            'INPUT.json',
            'INPUT.bin',
            'INPUT.txt',
        ]

        if folder_exists:
            # Create a temporary folder to save important files in
            Path(temporary_path).mkdir(parents=True, exist_ok=True)

            # Go through each file and save the ones that are important
            for entity in possible_input_keys:
                original_file_path = os.path.join(folder, entity)
                temp_file_path = os.path.join(temporary_path, entity)
                try:
                    await rename(original_file_path, temp_file_path)
                except Exception:
                    # Ignore
                    pass

            # Remove the original folder and all its content
            counter = 0
            temp_path_for_old_folder = os.path.join(folder, f'../__OLD_DEFAULT_{counter}__')
            done = False
            while not done:
                try:
                    await rename(folder, temp_path_for_old_folder)
                    done = True
                except Exception:
                    counter += 1
                    temp_path_for_old_folder = os.path.join(folder, f'../__OLD_DEFAULT_{counter}__')

            # Replace the temporary folder with the original folder
            await rename(temporary_path, folder)

            # Remove the old folder
            await self._batch_remove_files(temp_path_for_old_folder)

    async def _batch_remove_files(self, folder: str, counter: int = 0) -> None:
        folder_exists = await ospath.exists(folder)
        print(f'batch remove {folder}')
        if folder_exists:
            temporary_folder = folder if folder.startswith('__APIFY_TEMPORARY_') else os.path.join(folder, f'../__APIFY_TEMPORARY_{counter}__')

            try:
                # Rename the old folder to the new one to allow background deletions
                await rename(folder, temporary_folder)
            except Exception:
                # Folder exists already, try again with an incremented counter
                return await self._batch_remove_files(folder, counter + 1)

            await aioshutil.rmtree(temporary_folder, ignore_errors=True)
