from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from crawlee import service_locator
from crawlee._consts import METADATA_FILENAME

from apify import Actor, Configuration
from apify.storage_clients._file_system import ApifyFileSystemKeyValueStoreClient


async def test_purge_preserves_input_file_and_metadata() -> None:
    """Test that purge() preserves INPUT.json and metadata files but removes other files."""
    # Get the global configuration (storage directory is set by test fixtures)
    configuration = Configuration.get_global_configuration()

    kvs_storage_client = await ApifyFileSystemKeyValueStoreClient.open(
        id=None,
        name='test-kvs',
        alias=None,
        configuration=configuration,
    )

    # Create some test files in the KVS directory
    kvs_path = kvs_storage_client.path_to_kvs

    # Create various files
    input_file = kvs_path / f'{configuration.input_key}'
    input_metadata_file = kvs_path / f'{configuration.input_key}.{METADATA_FILENAME}.json'
    metadata_file = kvs_path / METADATA_FILENAME
    regular_file1 = kvs_path / 'regular_file1.json'
    regular_file2 = kvs_path / 'another_file.txt'

    # Write content to files
    await asyncio.to_thread(input_file.write_text, '{"test": "input"}')
    await asyncio.to_thread(input_metadata_file.write_text, 'some text content')
    await asyncio.to_thread(regular_file1.write_text, '{"test": "data1"}')
    await asyncio.to_thread(regular_file2.write_text, 'some text content')

    # Verify all files exist before purge
    assert input_file.exists()
    assert input_metadata_file.exists()
    assert metadata_file.exists()  # Should exist from client creation
    assert regular_file1.exists()
    assert regular_file2.exists()

    # Purge the key-value store
    await kvs_storage_client.purge()

    # Verify INPUT.json and metadata are preserved
    assert input_file.exists(), f'{configuration.input_key} should be preserved during purge'
    assert metadata_file.exists(), f'{METADATA_FILENAME} should be preserved during purge'

    # Verify other files are deleted
    assert not regular_file1.exists(), 'Regular files should be deleted during purge'
    assert not regular_file2.exists(), 'Regular files should be deleted during purge'

    # Verify INPUT.json content is unchanged
    input_content = await asyncio.to_thread(input_file.read_text)
    assert json.loads(input_content) == json.loads('{"test": "input"}')


@pytest.mark.parametrize('input_file_name', ['INPUT', 'INPUT.json'])
async def test_pre_existing_input_used_by_actor(input_file_name: str) -> None:
    configuration = Configuration()
    service_locator.set_configuration(configuration)

    # Create key-value store directory and make sure that it is empty
    path_to_input = Path(configuration.storage_dir) / 'key_value_stores' / 'default'
    path_to_input.mkdir(parents=True)
    assert list(path_to_input.glob('*')) == []

    pre_existing_input = {
        'foo': 'bar',
    }

    # Create pre-existing INPUT.json file
    (path_to_input / input_file_name).write_text(json.dumps(pre_existing_input))

    async with Actor():
        assert pre_existing_input == await Actor.get_input()

    # Make sure that the input file doesn't get renamed in the process and metadata are added
    assert set(path_to_input.glob('*')) == {
        path_to_input / '__metadata__.json',
        path_to_input / input_file_name,
        path_to_input / f'{input_file_name}.__metadata__.json',
    }
