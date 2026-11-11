from __future__ import annotations

from typing import TYPE_CHECKING

from apify import Actor

if TYPE_CHECKING:
    from .conftest import MakeActorFunction, RunActorFunction


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
        'actor/main.py': """
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


async def test_kvs_defaults(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        from apify.storages import KeyValueStore

        async with Actor:
            was_rebooted = await Actor.get_value('was_rebooted', default_value=False)

            kvs_1 = await Actor.open_key_value_store()
            kvs_2 = await KeyValueStore.open()

            assert kvs_1 is kvs_2

            if not was_rebooted:
                await kvs_1.set_value('key1', {'from': 'kvs_1'})
                await kvs_2.set_value('key2', {'from': 'kvs_2'})
                await Actor.set_value('was_rebooted', value=True)
                await Actor.reboot()

            kvs_11 = await Actor.open_key_value_store()
            kvs_22 = await KeyValueStore.open()

            assert kvs_11 is kvs_22
            assert kvs_1.id == kvs_11.id == kvs_2.id == kvs_22.id

            kvs_1_item = await kvs_11.get_value('key1')
            kvs_2_item = await kvs_22.get_value('key2')

            assert kvs_1_item == {'from': 'kvs_1'}
            assert kvs_2_item == {'from': 'kvs_2'}

    actor = await make_actor(label='kvs-defaults', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_kvs_aliases(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        from apify.storages import KeyValueStore

        async with Actor:
            was_rebooted = await Actor.get_value('was_rebooted', default_value=False)

            kvs_1 = await Actor.open_key_value_store(alias='my-alias-kvs-1')
            kvs_2 = await KeyValueStore.open(alias='my-alias-kvs-2')

            assert kvs_1 is not kvs_2
            assert kvs_1.id != kvs_2.id
            assert kvs_1.name is None
            assert kvs_2.name is None

            if not was_rebooted:
                await kvs_1.set_value('key1', {'from': 'kvs_1'})
                await kvs_2.set_value('key1', {'from': 'kvs_2'})
                await Actor.set_value('was_rebooted', value=True)
                await Actor.reboot()

            kvs_11 = await Actor.open_key_value_store(alias='my-alias-kvs-1')
            kvs_22 = await KeyValueStore.open(alias='my-alias-kvs-2')

            assert kvs_1.id == kvs_11.id
            assert kvs_11 is kvs_1

            assert kvs_2.id == kvs_22.id
            assert kvs_22 is kvs_2

            kvs_1_item = await kvs_11.get_value('key1')
            kvs_2_item = await kvs_22.get_value('key1')
            assert kvs_1_item == {'from': 'kvs_1'}
            assert kvs_2_item == {'from': 'kvs_2'}

    actor = await make_actor(label='kvs-aliases', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_use_state_survives_reboot(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """The state from `Actor.use_state()` is persisted before a reboot and loaded again in the next container."""

    async def main() -> None:
        async with Actor:
            run = await Actor.apify_client.run(Actor.configuration.actor_run_id or '').get()
            assert run is not None, 'The Actor could not read its own run.'

            state = await Actor.use_state({'containers': 0})
            containers = state['containers']
            assert isinstance(containers, int), f'state={dict(state)}'
            state['containers'] = containers + 1

            if run.stats.reboot_count == 0:
                state['before_reboot'] = ['a', 'b']
                await Actor.reboot()
            else:
                assert state.get('before_reboot') == ['a', 'b'], f'state={dict(state)}'

    actor = await make_actor(label='use-state-reboot', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'
    assert run_result.stats.reboot_count == 1

    state_record = await actor.last_run().key_value_store().get_record('APIFY_GLOBAL_STATE')
    assert state_record is not None
    assert state_record['value'] == {'containers': 2, 'before_reboot': ['a', 'b']}
