from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from apify_shared.consts import ApifyEnvVars
from crawlee import service_locator

from ._utils import generate_unique_resource_name
from apify import Actor
from apify.storage_clients import ApifyStorageClient
from apify.storage_clients._apify._alias_resolving import AliasResolver
from apify.storages import KeyValueStore

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from apify_client import ApifyClientAsync


@pytest.fixture
async def key_value_store_apify(apify_token: str, monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[KeyValueStore]:
    """Create an instance of the Apify key-value store on the platform and drop it when the test is finished."""
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_token)

    async with Actor:
        kvs = await KeyValueStore.open(storage_client=ApifyStorageClient())
        yield kvs
        await kvs.drop()


async def test_same_references_in_default_kvs(apify_token: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that opening the default KVS twice returns the same instance."""
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_token)

    async with Actor:
        kvs1 = await Actor.open_key_value_store()
        kvs2 = await Actor.open_key_value_store()
        assert kvs1 is kvs2


async def test_same_references_in_named_kvs(apify_token: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that opening a named KVS by name and then by ID returns the same instance."""
    kvs_name = generate_unique_resource_name('key-value-store')
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_token)

    async with Actor:
        kvs_by_name_1 = await Actor.open_key_value_store(name=kvs_name)
        try:
            kvs_by_name_2 = await Actor.open_key_value_store(name=kvs_name)
            assert kvs_by_name_1 is kvs_by_name_2

            kvs_1_metadata = await kvs_by_name_1.get_metadata()
            kvs_by_id_1 = await Actor.open_key_value_store(id=kvs_1_metadata.id)
            kvs_by_id_2 = await Actor.open_key_value_store(id=kvs_1_metadata.id)
            assert kvs_by_id_1 is kvs_by_name_1
            assert kvs_by_id_2 is kvs_by_id_1
        finally:
            await kvs_by_name_1.drop()


async def test_set_and_get_value_in_same_run(key_value_store_apify: KeyValueStore) -> None:
    """Test setting and getting values within the same Actor context."""
    kvs = key_value_store_apify
    await kvs.set_value('test', {'number': 123, 'string': 'a string', 'nested': {'test': 1}})
    value = await kvs.get_value('test')
    assert value['number'] == 123
    assert value['string'] == 'a string'
    assert value['nested']['test'] == 1


async def test_set_value_in_one_context_and_get_value_in_another(
    apify_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that values persisted in one Actor context can be retrieved in another."""
    kvs_name = generate_unique_resource_name('kvs')
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_token)

    # First context: set the value
    async with Actor:
        kvs = await Actor.open_key_value_store(name=kvs_name, force_cloud=True)
        kvs_id = (await kvs.get_metadata()).id
        await kvs.set_value('test', {'number': 123, 'string': 'a string', 'nested': {'test': 1}})

    # Reset service locator to simulate a fresh context
    service_locator._configuration = None
    service_locator._event_manager = None
    service_locator._storage_client = None
    service_locator.storage_instance_manager.clear_cache()
    AliasResolver._alias_map = {}
    AliasResolver._alias_init_lock = None

    # Second context: get the value
    try:
        async with Actor:
            kvs2 = await Actor.open_key_value_store(id=kvs_id, force_cloud=True)
            value = await kvs2.get_value('test')
            assert value['number'] == 123
            assert value['string'] == 'a string'
            assert value['nested']['test'] == 1
    finally:
        # Clean up
        service_locator._configuration = None
        service_locator._event_manager = None
        service_locator._storage_client = None
        service_locator.storage_instance_manager.clear_cache()
        AliasResolver._alias_map = {}
        AliasResolver._alias_init_lock = None
        async with Actor:
            kvs3 = await Actor.open_key_value_store(id=kvs_id, force_cloud=True)
            await kvs3.drop()


async def test_generate_public_url_for_kvs_record(key_value_store_apify: KeyValueStore) -> None:
    """Test that public URL generation works with proper HMAC signatures."""
    from apify._crypto import create_hmac_signature
    from apify.storage_clients._apify._models import ApifyKeyValueStoreMetadata

    kvs = key_value_store_apify
    record_key = 'public-record-key'

    metadata = await kvs.get_metadata()
    assert isinstance(metadata, ApifyKeyValueStoreMetadata)
    assert metadata.url_signing_secret_key is not None

    await kvs.set_value(record_key, {'exposedData': 'test'}, 'application/json')

    record_url = await kvs.get_public_url(record_key)
    signature = create_hmac_signature(metadata.url_signing_secret_key, record_key)

    public_api_url = Actor.configuration.api_public_base_url
    expected_record_url = f'{public_api_url}/v2/key-value-stores/{kvs.id}/records/{record_key}?signature={signature}'

    assert record_url == expected_record_url


async def test_force_cloud(
    apify_client_async: ApifyClientAsync,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that force_cloud creates storage in the cloud even when running locally."""
    assert apify_client_async.token is not None
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_client_async.token)

    key_value_store_name = generate_unique_resource_name('key-value-store')

    async with Actor:
        key_value_store = await Actor.open_key_value_store(name=key_value_store_name, force_cloud=True)
        key_value_store_id = (await key_value_store.get_metadata()).id

        await key_value_store.set_value('foo', 'bar')

    key_value_store_client = apify_client_async.key_value_store(key_value_store_id)

    try:
        key_value_store_details = await key_value_store_client.get()
        assert key_value_store_details is not None
        assert key_value_store_details.get('name') == key_value_store_name

        key_value_store_record = await key_value_store_client.get_record('foo')
        assert key_value_store_record is not None
        assert key_value_store_record['value'] == 'bar'
    finally:
        await key_value_store_client.delete()
