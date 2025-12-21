import asyncio
import json
import logging
from itertools import chain
from pathlib import Path

from typing_extensions import Self, override

from crawlee._consts import METADATA_FILENAME
from crawlee._utils.file import atomic_write, infer_mime_type, json_dumps
from crawlee.configuration import Configuration as CrawleeConfiguration
from crawlee.storage_clients._file_system import FileSystemKeyValueStoreClient
from crawlee.storage_clients.models import KeyValueStoreMetadata, KeyValueStoreRecord, KeyValueStoreRecordMetadata

from apify._configuration import Configuration as ApifyConfiguration

logger = logging.getLogger(__name__)


class ApifyFileSystemKeyValueStoreClient(FileSystemKeyValueStoreClient):
    """Apify-specific implementation of the `FileSystemKeyValueStoreClient`.

    The only difference is that it overrides the `purge` method to delete all files in the key-value store
    directory, except for the metadata file and the `INPUT.json` file.
    """

    def __init__(
        self,
        *,
        metadata: KeyValueStoreMetadata,
        path_to_kvs: Path,
        lock: asyncio.Lock,
    ) -> None:
        super().__init__(metadata=metadata, path_to_kvs=path_to_kvs, lock=lock)
        global_configuration = ApifyConfiguration.get_global_configuration()
        self._input_key = global_configuration.input_key
        self._input_key_filename = global_configuration.input_key

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

        if isinstance(configuration, ApifyConfiguration):
            client._input_key = configuration.input_key  # noqa: SLF001 - it's okay, this is a factory method
            input_key_filename = cls._get_input_key_file_name(
                path_to_kvs=client.path_to_kvs, configuration=configuration
            )
            client._input_key_filename = input_key_filename  # noqa: SLF001 - it's okay, this is a factory method
            input_file_path = client.path_to_kvs / input_key_filename
            input_file_metadata_path = client.path_to_kvs / f'{input_file_path}.{METADATA_FILENAME}'
            if input_file_path.exists() and not input_file_metadata_path.exists():
                await cls._create_missing_metadata_for_input_file(
                    key=configuration.input_key, record_path=input_file_path
                )

        return client  # ty: ignore[invalid-return-type]

    @override
    async def purge(self) -> None:
        """Purges the key-value store by deleting all its contents.

        It deletes all files in the key-value store directory, except for the metadata file and
        the input related file and its metadata.
        """
        async with self._lock:
            files_to_keep = {self._input_key_filename, f'{self._input_key_filename}.{METADATA_FILENAME}'}
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

    @override
    async def get_value(self, *, key: str) -> KeyValueStoreRecord | None:
        if key == self._input_key:
            # Potentially point to custom input file name instead
            key = self._input_key_filename
        return await super().get_value(key=key)

    @staticmethod
    async def _create_missing_metadata_for_input_file(key: str, record_path: Path) -> None:
        # Read the actual value
        try:
            content = await asyncio.to_thread(record_path.read_bytes)
        except FileNotFoundError:
            logger.warning(f'Input file disparaged on path: "{record_path}"')
            return

        # Figure out the metadata from the file content
        size = len(content)
        if record_path.suffix == '.json':
            value = json.loads(content.decode('utf-8'))
        elif record_path.suffix == '.txt':
            value = content.decode('utf-8')
        elif record_path.suffix == '':
            try:
                value = json.loads(content.decode('utf-8'))
            except json.JSONDecodeError:
                value = content
        else:
            value = content

        content_type = infer_mime_type(value)

        record_metadata = KeyValueStoreRecordMetadata(key=key, content_type=content_type, size=size)
        record_metadata_filepath = record_path.with_name(f'{record_path.name}.{METADATA_FILENAME}')
        record_metadata_content = await json_dumps(record_metadata.model_dump())

        # Write the record metadata to the file.
        await atomic_write(record_metadata_filepath, record_metadata_content)

    @staticmethod
    def _get_input_key_file_name(path_to_kvs: Path, configuration: ApifyConfiguration) -> str:
        found_input_files = set()
        for file_path in chain(
            path_to_kvs.glob(f'{configuration.input_key}.*'), path_to_kvs.glob(f'{configuration.input_key}')
        ):
            if str(file_path).endswith(METADATA_FILENAME):
                # Ignore metadata files
                continue
            found_input_files.add(file_path.name)

        if len(found_input_files) > 1:
            raise RuntimeError(f'Only one input file is allowed. Following input files found: {found_input_files}')

        if len(found_input_files) == 1:
            return found_input_files.pop()

        # No custom input file found, return the default input key
        return configuration.input_key
