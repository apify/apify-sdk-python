from apify import Actor

from .conftest import ActorFactory


class TestActorOpenKeyValueStore:
    async def test_same_references(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            async with Actor:
                kvs1 = await Actor.open_key_value_store()
                kvs2 = await Actor.open_key_value_store()
                assert kvs1 is kvs2

        actor = await make_actor('kvs-same-references', main_func=main)

        run_result = await actor.call()
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
        async def main() -> None:
            async with Actor:
                input_object = await Actor.get_input()
                assert input_object is not None
                assert input_object['number'] == 123
                assert input_object['string'] == 'a string'
                assert input_object['nested']['test'] == 1

        actor = await make_actor('actor-get-input', main_func=main)

        run_result = await actor.call(run_input={'number': 123, 'string': 'a string', 'nested': {'test': 1}})
        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'
