from apify import Actor

from ._utils import generate_unique_resource_name
from .conftest import ActorFactory


class TestActorOpenKeyValueStore:
    async def test_same_references_default(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            async with Actor:
                kvs1 = await Actor.open_key_value_store()
                kvs2 = await Actor.open_key_value_store()
                assert kvs1 is kvs2

        actor = await make_actor('kvs-same-ref-default', main_func=main)

        run_result = await actor.call()
        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'

    async def test_same_references_named(self, make_actor: ActorFactory) -> None:
        kvs_name = generate_unique_resource_name('key-value-store')

        async def main() -> None:
            async with Actor:
                input_object = await Actor.get_input()
                kvs_name = input_object['kvsName']
                kvs1 = await Actor.open_key_value_store(kvs_name)
                kvs2 = await Actor.open_key_value_store(kvs_name)
                assert kvs1 is kvs2
                await kvs1.drop()

        actor = await make_actor('kvs-same-ref-named', main_func=main)

        run_result = await actor.call(run_input={'kvsName': kvs_name})
        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'


class TestActorGetSetValue:
    async def test_actor_get_set_value_simple(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            async with Actor:
                await Actor.set_value('test', {'number': 123, 'string': 'a string', 'nested': {'test': 1}})
                value = await Actor.get_value('test')
                assert value['number'] == 123
                assert value['string'] == 'a string'
                assert value['nested']['test'] == 1

        actor = await make_actor('actor-get-set-value', main_func=main)

        run_result = await actor.call()
        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'

    async def test_actor_get_set_value_complex(self, make_actor: ActorFactory) -> None:
        async def main_set() -> None:
            async with Actor:
                await Actor.set_value('test', {'number': 123, 'string': 'a string', 'nested': {'test': 1}})

        actor_set = await make_actor('actor-set-value', main_func=main_set)

        run_result_set = await actor_set.call()
        assert run_result_set is not None
        assert run_result_set['status'] == 'SUCCEEDED'
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
                kvs = await Actor.open_key_value_store(input_object['kvs-id'])
                value = await kvs.get_value('test')
                assert value['number'] == 123
                assert value['string'] == 'a string'
                assert value['nested']['test'] == 1

        actor_get = await make_actor('actor-get-value', main_func=main_get)
        default_kvs_info = await actor_set.last_run().key_value_store().get()
        assert default_kvs_info is not None

        run_result_get = await actor_get.call(run_input={'kvs-id': default_kvs_info['id']})
        assert run_result_get is not None
        assert run_result_get['status'] == 'SUCCEEDED'


class TestActorGetInput:
    async def test_actor_get_input(self, make_actor: ActorFactory) -> None:
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
        actor = await make_actor('actor-get-input', source_files=actor_source_files)

        run_result = await actor.call(run_input={
            'number': 123,
            'string': 'a string',
            'nested': {'test': 1},
            'password': 'very secret',
        })
        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'
