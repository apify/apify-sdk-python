from __future__ import annotations

import asyncio
from typing import cast

import pytest

from crawlee import service_locator
from crawlee.storages import Dataset, KeyValueStore, RequestQueue

from apify import Actor, Configuration
from apify._configuration import ActorStorages
from apify.storage_clients import ApifyStorageClient, MemoryStorageClient, SmartApifyStorageClient
from apify.storage_clients._apify._alias_resolving import AliasResolver


@pytest.mark.parametrize(
    'storage_type',
    [Dataset, KeyValueStore, RequestQueue],
)
async def test_alias_concurrent_creation_local(
    storage_type: Dataset | KeyValueStore | RequestQueue, apify_token: str
) -> None:
    """Test that storages created with same alias are created only once even when created concurrently."""
    service_locator.set_configuration(Configuration(token=apify_token))
    service_locator.set_storage_client(ApifyStorageClient())
    tasks = [asyncio.create_task(storage_type.open(alias='test')) for _ in range(2)]

    storages = await asyncio.gather(*tasks)
    unique_storage_ids = {storage.id for storage in storages}
    try:
        # Only one aliased storage should be created.
        assert len(unique_storage_ids) == 1

        # Clean up
        await storages[0].drop()
    except AssertionError:
        for storage in storages:
            await storage.drop()


@pytest.mark.parametrize(
    'storage_type',
    [Dataset, KeyValueStore, RequestQueue],
)
async def test_unnamed_default_without_config(
    storage_type: Dataset | KeyValueStore | RequestQueue, apify_token: str
) -> None:
    """Test that default Apify storage used locally is unnamed storage."""
    service_locator.set_configuration(Configuration(token=apify_token))
    service_locator.set_storage_client(ApifyStorageClient())

    # Open storage and make sure it has no name and it has id
    storage = await storage_type.open()
    assert storage.name is None
    assert storage.id

    # Make sure the same instance is returned when opened again without name or alias
    storage_again = await storage_type.open()
    assert storage is storage_again

    await storage.drop()


@pytest.mark.parametrize(
    'storage_type',
    [Dataset, KeyValueStore, RequestQueue],
)
async def test_aliases_not_stored_on_platform_when_local(
    storage_type: Dataset | KeyValueStore | RequestQueue, apify_token: str
) -> None:
    """Test that default Apify storage used locally is not persisting aliases to Apify based default KVS."""
    service_locator.set_configuration(Configuration(token=apify_token))
    async with Actor(configure_logging=False):
        await storage_type.open(alias='test')
        default_kvs = await Actor.open_key_value_store(force_cloud=True)

        # The default KVS should be empty
        assert len(await default_kvs.list_keys()) == 0


async def test_actor_full_explicit_storage_init(apify_token: str) -> None:
    service_locator.set_configuration(Configuration(token=apify_token))
    service_locator.set_storage_client(
        SmartApifyStorageClient(
            local_storage_client=MemoryStorageClient(),
            cloud_storage_client=ApifyStorageClient(request_queue_access='shared'),
        )
    )
    async with Actor:
        # If service locator was already set with SmartApifyStorageClient, the actor will use it.
        # Storages should be different when force_cloud is used outside the Apify platform
        assert await Actor.open_dataset() is not await Actor.open_dataset(force_cloud=True)
        assert await Actor.open_key_value_store() is not await Actor.open_key_value_store(force_cloud=True)
        assert await Actor.open_request_queue() is not await Actor.open_request_queue(force_cloud=True)


async def test_actor_full_explicit_storage_init_same_client(apify_token: str) -> None:
    service_locator.set_configuration(Configuration(token=apify_token))
    service_locator.set_storage_client(
        SmartApifyStorageClient(
            local_storage_client=ApifyStorageClient(request_queue_access='shared'),
            cloud_storage_client=ApifyStorageClient(request_queue_access='shared'),
        )
    )
    async with Actor:
        # If service locator was already set with SmartApifyStorageClient, the actor will use it.
        # Storages should be same as the equivalent storage client is for both local and cloud storage client
        assert await Actor.open_dataset() is await Actor.open_dataset(force_cloud=True)
        assert await Actor.open_key_value_store() is await Actor.open_key_value_store(force_cloud=True)
        assert await Actor.open_request_queue() is await Actor.open_request_queue(force_cloud=True)


async def test_actor_partial_explicit_cloud_storage_init(apify_token: str) -> None:
    service_locator.set_configuration(Configuration(token=apify_token))
    service_locator.set_storage_client(ApifyStorageClient(request_queue_access='shared'))
    with pytest.raises(
        RuntimeError, match=r'^The storage client in the service locator has to be instance of SmartApifyStorageClient'
    ):
        async with Actor:
            # If service locator was explicitly set to something different than SmartApifyStorageClient, raise an error.
            ...


async def test_actor_implicit_storage_init(apify_token: str) -> None:
    service_locator.set_configuration(Configuration(token=apify_token))
    async with Actor:
        assert await Actor.open_dataset() is not await Actor.open_dataset(force_cloud=True)
        assert await Actor.open_key_value_store() is not await Actor.open_key_value_store(force_cloud=True)
        assert await Actor.open_request_queue() is not await Actor.open_request_queue(force_cloud=True)


async def test_actor_storages_alias_resolving(apify_token: str) -> None:
    """Test that `AliasResolver.register_aliases` correctly updates default KVS with Actor storages."""

    # Actor storages
    datasets = {'default': 'default_dataset_id', 'custom': 'custom_dataset_id'}
    request_queues = {'default': 'default_dataset_id', 'custom': 'custom_dataset_id'}
    key_value_stores = {'default': 'default_dataset_id', 'custom': 'custom_dataset_id'}

    # Set up the configuration and storage client for the test
    configuration = Configuration(
        default_key_value_store_id='default_kvs_id',
        token=apify_token,
        actor_storages=ActorStorages(
            datasets=datasets, request_queues=request_queues, key_value_stores=key_value_stores
        ),
    )
    storage_client = ApifyStorageClient()
    service_locator.set_configuration(configuration)
    service_locator.set_storage_client(storage_client)

    client_cache_key = cast('tuple', storage_client.get_storage_client_cache_key(configuration))[-1]
    # Add some unrelated pre-existing alias mapping (it should be preserved after registering aliases)
    pre_existing_mapping = {f'KeyValueStore,pre_existing_alias,{client_cache_key}': 'pre_existing_id'}

    default_kvs = await KeyValueStore.open(configuration=configuration, storage_client=storage_client)
    await default_kvs.set_value(AliasResolver._ALIAS_MAPPING_KEY, pre_existing_mapping)

    # Construct the expected mapping
    expected_mapping = {}
    for storage_type, storage_map in (
        ('Dataset', datasets),
        ('KeyValueStore', key_value_stores),
        ('RequestQueue', request_queues),
    ):
        for storage_alias, storage_id in storage_map.items():
            expected_mapping[
                ','.join(
                    (storage_type, '__default__' if storage_alias == 'default' else storage_alias, client_cache_key)
                )
            ] = storage_id
    expected_mapping.update(pre_existing_mapping)

    try:
        configuration.default_key_value_store_id = default_kvs.id
        await AliasResolver.register_aliases(configuration=configuration)
        assert await default_kvs.get_value(AliasResolver._ALIAS_MAPPING_KEY) == expected_mapping
    finally:
        await default_kvs.drop()
