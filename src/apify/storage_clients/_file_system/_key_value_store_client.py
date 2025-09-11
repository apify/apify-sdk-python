import asyncio
import json
from pathlib import Path

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

        # First try to find the alternative format of the input file and process it if it exists.
        for file_path in self.path_to_kvs.glob('*'):
            if file_path.name == f'{kvs_input_key}.json':
                await self._process_input_json(file_path)

        async with self._lock:
            for file_path in self.path_to_kvs.glob('*'):
                if file_path.name in {METADATA_FILENAME, kvs_input_key, f'{kvs_input_key}.{METADATA_FILENAME}'}:
                    continue
                if file_path.is_file():
                    await asyncio.to_thread(file_path.unlink, missing_ok=True)

            await self._update_metadata(
                update_accessed_at=True,
                update_modified_at=True,
            )

    async def _process_input_json(self, path: Path) -> None:
        """Process simple input json file to format expected by the FileSystemKeyValueStoreClient.

        For example: INPUT.json -> INPUT, INPUT.json.metadata
        """
        try:
            f = await asyncio.to_thread(path.open)
            input_data = json.load(f)
        finally:
            f.close()
        await asyncio.to_thread(path.unlink, missing_ok=True)
        await self.set_value(key=path.stem, value=input_data)
