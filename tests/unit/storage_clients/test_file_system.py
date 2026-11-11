from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

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


@pytest.mark.parametrize(
    'input_file_name',
    [pytest.param('INPUT', id='bare'), pytest.param('INPUT.json', id='json')],
)
@pytest.mark.parametrize(
    'pre_existing_input',
    [
        pytest.param({'foo': 'bar'}, id='object'),
        pytest.param('', id='empty-string'),
        pytest.param(0, id='zero-integer'),
        pytest.param(1.5, id='float'),
        pytest.param(False, id='false'),
        pytest.param(None, id='null'),
    ],
)
async def test_pre_existing_input_used_by_actor(input_file_name: str, pre_existing_input: Any) -> None:
    """Pre-existing JSON input preserves its value, type, bytes, and serialization metadata."""
    configuration = Configuration()
    service_locator.set_configuration(configuration)

    # Create key-value store directory and make sure that it is empty
    path_to_input = Path(configuration.storage_dir) / 'key_value_stores' / 'default'
    path_to_input.mkdir(parents=True)
    assert list(path_to_input.glob('*')) == []

    input_file = path_to_input / input_file_name
    input_bytes = json.dumps(pre_existing_input).encode('utf-8')
    input_file.write_bytes(input_bytes)

    async with Actor():
        actual_input = await Actor.get_input()
        assert actual_input == pre_existing_input
        assert type(actual_input) is type(pre_existing_input)
        store = await Actor.open_key_value_store()
        stored_input = await store.get_value(configuration.input_key)
        assert stored_input == pre_existing_input
        assert type(stored_input) is type(pre_existing_input)

    assert input_file.read_bytes() == input_bytes
    metadata = json.loads((path_to_input / f'{input_file_name}.{METADATA_FILENAME}').read_text())
    assert metadata['content_type'] == 'application/json; charset=utf-8'
    assert metadata['key'] == configuration.input_key
    assert metadata['size'] == len(input_bytes)

    # Make sure that the input file doesn't get renamed in the process and metadata are added
    assert set(path_to_input.glob('*')) == {
        path_to_input / '__metadata__.json',
        path_to_input / input_file_name,
        path_to_input / f'{input_file_name}.__metadata__.json',
    }


@pytest.mark.parametrize(
    'input_bytes',
    [pytest.param(b'hello', id='plain'), pytest.param('hello'.encode('utf-16'), id='utf16')],
)
async def test_pre_existing_non_json_input_used_by_actor(input_bytes: bytes) -> None:
    """Bare non-JSON input preserves its bytes and uses binary serialization metadata."""
    configuration = Configuration()
    service_locator.set_configuration(configuration)
    path_to_input = Path(configuration.storage_dir) / 'key_value_stores' / 'default'
    path_to_input.mkdir(parents=True)
    input_file = path_to_input / 'INPUT'
    input_file.write_bytes(input_bytes)

    async with Actor():
        actual_input = await Actor.get_input()
        assert actual_input == input_bytes
        assert type(actual_input) is bytes
        store = await Actor.open_key_value_store()
        stored_input = await store.get_value(configuration.input_key)
        assert stored_input == input_bytes
        assert type(stored_input) is bytes

    assert input_file.read_bytes() == input_bytes
    metadata = json.loads((path_to_input / f'INPUT.{METADATA_FILENAME}').read_text())
    assert metadata['content_type'] == 'application/octet-stream'
    assert metadata['key'] == configuration.input_key
    assert metadata['size'] == len(input_bytes)


async def test_set_value_with_input_key_targets_existing_input_file() -> None:
    """`set_value` with the input key overwrites the existing `INPUT.json` instead of creating a duplicate."""
    configuration = Configuration.get_global_configuration()

    # Pre-create a custom-named input file (with extension) before opening the client.
    kvs_path = Path(configuration.storage_dir) / 'key_value_stores' / 'default'
    kvs_path.mkdir(parents=True)
    (kvs_path / 'INPUT.json').write_text(json.dumps({'foo': 'bar'}))

    client = await ApifyFileSystemKeyValueStoreClient.open(id=None, name=None, alias=None, configuration=configuration)
    await client.set_value(key=configuration.input_key, value={'foo': 'baz'})

    # The existing input file is overwritten in place. No second input file (e.g. `INPUT`) is created.
    assert set(kvs_path.glob('*')) == {
        kvs_path / '__metadata__.json',
        kvs_path / 'INPUT.json',
        kvs_path / f'INPUT.json.{METADATA_FILENAME}',
    }

    # Reopening must not raise "Only one input file is allowed", i.e. no duplicate input file was created.
    client = await ApifyFileSystemKeyValueStoreClient.open(id=None, name=None, alias=None, configuration=configuration)
    record = await client.get_value(key=configuration.input_key)
    assert record is not None
    assert record.value == {'foo': 'baz'}


async def test_record_exists_and_delete_value_target_existing_input_file() -> None:
    """`record_exists` and `delete_value` with the input key operate on the existing `INPUT.json`."""
    configuration = Configuration.get_global_configuration()

    kvs_path = Path(configuration.storage_dir) / 'key_value_stores' / 'default'
    kvs_path.mkdir(parents=True)
    (kvs_path / 'INPUT.json').write_text(json.dumps({'foo': 'bar'}))

    client = await ApifyFileSystemKeyValueStoreClient.open(id=None, name=None, alias=None, configuration=configuration)
    assert await client.record_exists(key=configuration.input_key) is True

    await client.delete_value(key=configuration.input_key)
    assert await client.record_exists(key=configuration.input_key) is False
    assert not (kvs_path / 'INPUT.json').exists()


async def test_pre_existing_input_metadata_is_preserved() -> None:
    """Opening an input record respects its explicit content type and leaves its metadata unchanged."""
    configuration = Configuration.get_global_configuration()
    kvs_path = Path(configuration.storage_dir) / 'key_value_stores' / 'default'
    kvs_path.mkdir(parents=True)
    input_file = kvs_path / 'INPUT.json'
    input_file.write_bytes(b'42')
    metadata_file = kvs_path / f'INPUT.json.{METADATA_FILENAME}'
    metadata_bytes = json.dumps(
        {'key': configuration.input_key, 'content_type': 'text/plain; charset=utf-8', 'size': 2}
    ).encode('utf-8')
    metadata_file.write_bytes(metadata_bytes)

    client = await ApifyFileSystemKeyValueStoreClient.open(id=None, name=None, alias=None, configuration=configuration)
    record = await client.get_value(key=configuration.input_key)

    assert record is not None
    assert record.value == '42'
    assert input_file.read_bytes() == b'42'
    assert metadata_file.read_bytes() == metadata_bytes


async def test_malformed_json_input_does_not_create_metadata() -> None:
    """Malformed JSON input raises without changing the input or creating record metadata."""
    configuration = Configuration.get_global_configuration()
    kvs_path = Path(configuration.storage_dir) / 'key_value_stores' / 'default'
    kvs_path.mkdir(parents=True)
    input_file = kvs_path / 'INPUT.json'
    input_file.write_bytes(b'{not json')

    with pytest.raises(json.JSONDecodeError):
        await ApifyFileSystemKeyValueStoreClient.open(id=None, name=None, alias=None, configuration=configuration)

    assert input_file.read_bytes() == b'{not json'
    assert not (kvs_path / f'INPUT.json.{METADATA_FILENAME}').exists()
