import asyncio

from typing_extensions import override

from crawlee._consts import METADATA_FILENAME
from crawlee.storage_clients._file_system import FileSystemKeyValueStoreClient

from apify._configuration import Configuration


class ApifyFileSystemKeyValueStoreClient(FileSystemKeyValueStoreClient):
    """Apify-specific implementation of the `FileSystemKeyValueStoreClient`.

    The only difference is that it overrides the `purge` method to delete all files in the key-value store
    directory, except for the metadata file and the `INPUT.json` file.
    """

    @override
    async def purge(self) -> None:
        """Purges the key-value store by deleting all its contents.

        It deletes all files in the key-value store directory, except for the metadata file and
        the `INPUT.json` file. It also updates the metadata to reflect that the store has been purged.
        """
        kvs_input_key = Configuration.get_global_configuration().input_key
        async with self._lock:
            for file_path in self.path_to_kvs.glob('*'):
                if file_path.name in {METADATA_FILENAME, f'{kvs_input_key}.json'}:
                    continue
                if file_path.is_file():
                    await asyncio.to_thread(file_path.unlink, missing_ok=True)

            await self._update_metadata(
                update_accessed_at=True,
                update_modified_at=True,
            )
