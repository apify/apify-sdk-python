import asyncio
import json
import logging

from more_itertools import flatten
from typing_extensions import Self, override

from crawlee._consts import METADATA_FILENAME
from crawlee.configuration import Configuration as CrawleeConfiguration
from crawlee.storage_clients._file_system import FileSystemKeyValueStoreClient
from crawlee.storage_clients.models import KeyValueStoreRecord

from apify._configuration import Configuration

logger = logging.getLogger(__name__)


class ApifyFileSystemKeyValueStoreClient(FileSystemKeyValueStoreClient):
    """Apify-specific implementation of the `FileSystemKeyValueStoreClient`.

    The only difference is that it overrides the `purge` method to delete all files in the key-value store
    directory, except for the metadata file and the `INPUT.json` file.
    """

    @override
    @classmethod
    async def open(
        cls,
        *,
        id: str | None,
        name: str | None,
        alias: str | None,
        configuration: CrawleeConfiguration,
    ) -> Self:
        client = await super().open(id=id, name=name, alias=alias, configuration=configuration)

        await client._sanitize_input_json_files()  # noqa: SLF001 - it's okay, this is a factory method

        return client

    @override
    async def purge(self) -> None:
        """Purges the key-value store by deleting all its contents.

        It deletes all files in the key-value store directory, except for the metadata file and
        the `INPUT.json` file. It also updates the metadata to reflect that the store has been purged.
        """
        configuration = Configuration.get_global_configuration()

        async with self._lock:
            files_to_keep = set(
                flatten([key, f'{key}.{METADATA_FILENAME}'] for key in configuration.input_key_candidates)
            )
            files_to_keep.add(METADATA_FILENAME)

            for file_path in self.path_to_kvs.glob('*'):
                if file_path.name in files_to_keep:
                    continue
                if file_path.is_file():
                    await asyncio.to_thread(file_path.unlink, missing_ok=True)

            await self._update_metadata(
                update_accessed_at=True,
                update_modified_at=True,
            )

    async def _sanitize_input_json_files(self) -> None:
        """Handle missing metadata for input files."""
        configuration = Configuration.get_global_configuration()
        alternative_keys = configuration.input_key_candidates - {configuration.canonical_input_key}

        if (self.path_to_kvs / configuration.canonical_input_key).exists():
            # Refresh metadata to prevent inconsistencies
            input_data = await asyncio.to_thread(
                lambda: json.loads((self.path_to_kvs / configuration.canonical_input_key).read_text())
            )
            await self.set_value(key=configuration.canonical_input_key, value=input_data)

            for alternative_key in alternative_keys:
                if (alternative_input_file := self.path_to_kvs / alternative_key).exists():
                    logger.warning(f'Redundant input file found: {alternative_input_file}')
        else:
            for alternative_key in alternative_keys:
                alternative_input_file = self.path_to_kvs / alternative_key

                # Only process files that actually exist
                if alternative_input_file.exists():
                    # Refresh metadata to prevent inconsistencies
                    with alternative_input_file.open() as f:
                        input_data = await asyncio.to_thread(lambda: json.load(f))
                    await self.set_value(key=alternative_key, value=input_data)

    @override
    async def get_value(self, *, key: str) -> KeyValueStoreRecord | None:
        configuration = Configuration.get_global_configuration()

        if key in configuration.input_key_candidates:
            for candidate in configuration.input_key_candidates:
                value = await super().get_value(key=candidate)
                if value is not None:
                    return value

        return await super().get_value(key=key)
