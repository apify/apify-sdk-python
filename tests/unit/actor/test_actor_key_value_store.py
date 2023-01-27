import pytest

from apify import Actor
from apify._utils import _json_dumps
from apify.memory_storage import MemoryStorage


# NOTE: We only test the key-value store methond available on Actor class/instance. Actual tests for the implementations are in storages/.
class TestOpenKeyValueStore:

    async def test_same_references(self) -> None:
        async with Actor:
            kvs1 = await Actor.open_key_value_store()
            kvs2 = await Actor.open_key_value_store()
            assert kvs1 is kvs2
            kvs_name = 'non-default'
            kvs_named1 = await Actor.open_key_value_store(kvs_name)
            kvs_named2 = await Actor.open_key_value_store(kvs_name)
            assert kvs_named1 is kvs_named2


class TestKeyValueStoreOnActor:

    async def test_throws_without_init(self) -> None:
        with pytest.raises(RuntimeError):
            await Actor.open_key_value_store()

    async def test_get_set_value(self) -> None:
        my_actor = Actor()
        test_key = 'test_key'
        test_value = 'test_value'
        test_content_type = 'text/plain'
        async with my_actor:
            await my_actor.set_value(key=test_key, value=test_value, content_type=test_content_type)
            value = await my_actor.get_value(key=test_key)
            assert value == test_value

    async def test_get_input(self, memory_storage: MemoryStorage) -> None:
        input_key = 'INPUT'
        test_input = {'foo': 'bar'}
        kvs_info = await memory_storage.key_value_stores().get_or_create(name='default')
        await memory_storage.key_value_store(kvs_info['id']).set_record(key=input_key, value=_json_dumps(test_input), content_type='application/json')
        my_actor = Actor()
        async with my_actor:
            input = await my_actor.get_input()
            assert input['foo'] == test_input['foo']
