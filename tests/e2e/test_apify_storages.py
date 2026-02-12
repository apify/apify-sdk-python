from .conftest import MakeActorFunction, RunActorFunction


async def test_actor_full_explicit_storage_init_on_platform(
    make_actor: MakeActorFunction, run_actor: RunActorFunction
) -> None:
    async def main() -> None:
        from crawlee import service_locator

        from apify import Actor
        from apify.storage_clients import ApifyStorageClient, MemoryStorageClient, SmartApifyStorageClient

        service_locator.set_storage_client(
            SmartApifyStorageClient(
                local_storage_client=MemoryStorageClient(),
                cloud_storage_client=ApifyStorageClient(request_queue_access='shared'),
            )
        )
        async with Actor:
            # Storages should be same as the cloud client is used on the platform
            assert await Actor.open_dataset() is await Actor.open_dataset(force_cloud=True)
            assert await Actor.open_key_value_store() is await Actor.open_key_value_store(force_cloud=True)
            assert await Actor.open_request_queue() is await Actor.open_request_queue(force_cloud=True)

    actor = await make_actor(label='explicit_storage_init', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'
