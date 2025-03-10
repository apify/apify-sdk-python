from __future__ import annotations

from typing import TYPE_CHECKING

from apify_shared.consts import ApifyEnvVars

from ._utils import generate_unique_resource_name
from apify import Actor

if TYPE_CHECKING:
    import pytest

    from apify_client import ApifyClientAsync

    from .conftest import MakeActorFunction, RunActorFunction


async def test_same_references_in_default_kvs(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        async with Actor:
            kvs1 = await Actor.open_key_value_store()
            kvs2 = await Actor.open_key_value_store()
            assert kvs1 is kvs2

    actor = await make_actor(label='kvs-same-ref-default', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_same_references_in_named_kvs(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    kvs_name = generate_unique_resource_name('key-value-store')

    async def main() -> None:
        async with Actor:
            input_object = await Actor.get_input()
            kvs_name = input_object['kvsName']
            kvs_by_name_1 = await Actor.open_key_value_store(name=kvs_name)
            kvs_by_name_2 = await Actor.open_key_value_store(name=kvs_name)
            assert kvs_by_name_1 is kvs_by_name_2

            kvs_by_id_1 = await Actor.open_key_value_store(id=kvs_by_name_1._id)
            kvs_by_id_2 = await Actor.open_key_value_store(id=kvs_by_name_1._id)
            assert kvs_by_id_1 is kvs_by_name_1
            assert kvs_by_id_2 is kvs_by_id_1

            await kvs_by_name_1.drop()

    actor = await make_actor(label='kvs-same-ref-named', main_func=main)
    run_result = await run_actor(actor, run_input={'kvsName': kvs_name})

    assert run_result.status == 'SUCCEEDED'


async def test_force_cloud(
    apify_client_async: ApifyClientAsync,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert apify_client_async.token is not None
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_client_async.token)

    key_value_store_name = generate_unique_resource_name('key_value_store')

    async with Actor:
        key_value_store = await Actor.open_key_value_store(name=key_value_store_name, force_cloud=True)
        key_value_store_id = key_value_store._id

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


async def test_set_and_get_value_in_same_run(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        async with Actor:
            await Actor.set_value('test', {'number': 123, 'string': 'a string', 'nested': {'test': 1}})
            value = await Actor.get_value('test')
            assert value['number'] == 123
            assert value['string'] == 'a string'
            assert value['nested']['test'] == 1

    actor = await make_actor(label='actor-get-set-value', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_set_value_in_one_run_and_get_value_in_another(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main_set() -> None:
        async with Actor:
            await Actor.set_value('test', {'number': 123, 'string': 'a string', 'nested': {'test': 1}})

    actor_set = await make_actor(label='actor-set-value', main_func=main_set)
    run_result_set = await run_actor(actor_set)

    assert run_result_set.status == 'SUCCEEDED'

    # Externally check if the value is present in key-value store
    test_record = await actor_set.last_run().key_value_store().get_record('test')
    assert test_record is not None
    test_value = test_record['value']
    assert test_value['number'] == 123
    assert test_value['string'] == 'a string'
    assert test_value['nested']['test'] == 1

    async def main_get() -> None:
        async with Actor:
            input_object = await Actor.get_input()
            # Access KVS of the previous 'set' run
            kvs = await Actor.open_key_value_store(id=input_object['kvs-id'])
            value = await kvs.get_value('test')
            assert value['number'] == 123
            assert value['string'] == 'a string'
            assert value['nested']['test'] == 1

    actor_get = await make_actor(label='actor-get-value', main_func=main_get)
    default_kvs_info = await actor_set.last_run().key_value_store().get()
    assert default_kvs_info is not None

    run_result_get = await run_actor(actor_get, run_input={'kvs-id': default_kvs_info['id']})

    assert run_result_get.status == 'SUCCEEDED'


async def test_actor_get_input_from_run(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    actor_source_files = {
        'INPUT_SCHEMA.json': """
            {
                "title": "Actor get input test",
                "type": "object",
                "schemaVersion": 1,
                "properties": {
                    "password": {
                            "title": "Password",
                            "type": "string",
                            "description": "A secret, encrypted input field",
                            "editor": "textfield",
                            "isSecret": true
                        }
                },
                "required": ["password"]
            }
        """,
        'src/main.py': """
            import asyncio
            from apify import Actor

            async def main():
                async with Actor:
                    input_object = await Actor.get_input()
                    assert input_object is not None
                    assert input_object['number'] == 123
                    assert input_object['string'] == 'a string'
                    assert input_object['nested']['test'] == 1
                    assert input_object['password'] == 'very secret'
        """,
    }
    actor = await make_actor(label='actor-get-input', source_files=actor_source_files)

    run_result = await run_actor(
        actor,
        run_input={
            'number': 123,
            'string': 'a string',
            'nested': {'test': 1},
            'password': 'very secret',
        },
    )

    assert run_result.status == 'SUCCEEDED'


async def test_generate_public_url_for_kvs_record(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        from apify._crypto import create_hmac_signature

        async with Actor:
            public_api_url = Actor.config.api_public_base_url
            default_store_id = Actor.config.default_key_value_store_id
            record_key = 'public-record-key'

            store = await Actor.open_key_value_store()

            assert isinstance(store.storage_object.model_extra, dict)
            url_signing_secret_key = store.storage_object.model_extra.get('urlSigningSecretKey')
            assert url_signing_secret_key is not None

            await store.set_value(record_key, {'exposedData': 'test'}, 'application/json')

            record_url = await store.get_public_url(record_key)

            signature = create_hmac_signature(url_signing_secret_key, record_key)
            assert (
                record_url
                == f'{public_api_url}/v2/key-value-stores/{default_store_id}/records/{record_key}?signature={signature}'
            )

    actor = await make_actor(label='kvs-get-public-url', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'
