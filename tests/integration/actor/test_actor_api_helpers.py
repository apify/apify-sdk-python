from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from crawlee._utils.crypto import crypto_random_object_id

from .._utils import generate_unique_resource_name
from apify import Actor
from apify._models import ActorRun

if TYPE_CHECKING:
    from apify_client import ApifyClientAsync

    from .conftest import MakeActorFunction, RunActorFunction


async def test_actor_reports_running_on_platform(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        async with Actor:
            assert Actor.is_at_home() is True

    actor = await make_actor(label='is-at-home', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_actor_retrieves_env_vars(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        async with Actor:
            env_dict = Actor.get_env()

            assert env_dict.get('is_at_home') is True
            assert env_dict.get('token') is not None
            assert env_dict.get('events_websocket_url') is not None
            assert env_dict.get('input_key') is not None

            assert len(env_dict.get('id', '')) == 17
            assert len(env_dict.get('build_id', '')) == 17
            assert len(env_dict.get('run_id', '')) == 17
            assert len(env_dict.get('user_id', '')) == 17

    actor = await make_actor(label='get-env', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_actor_creates_new_client_instance(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        import os

        from apify_shared.consts import ActorEnvVars

        async with Actor:
            new_client = Actor.new_client()
            assert new_client is not Actor.apify_client

            default_key_value_store_id = os.getenv(ActorEnvVars.DEFAULT_KEY_VALUE_STORE_ID)
            assert default_key_value_store_id is not None
            kv_store_client = new_client.key_value_store(default_key_value_store_id)
            await kv_store_client.set_record('OUTPUT', 'TESTING-OUTPUT')

    actor = await make_actor(label='new-client', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'

    output_record = await actor.last_run().key_value_store().get_record('OUTPUT')
    assert output_record is not None
    assert output_record['value'] == 'TESTING-OUTPUT'


async def test_actor_sets_status_message(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        async with Actor:
            actor_input = await Actor.get_input() or {}
            await Actor.set_status_message('testing-status-message', **actor_input)

    actor = await make_actor(label='set-status-message', main_func=main)
    run_result_1 = await run_actor(actor)

    assert run_result_1.status == 'SUCCEEDED'
    assert run_result_1.status_message == 'testing-status-message'
    assert run_result_1.is_status_message_terminal is None

    run_result_2 = await run_actor(actor, run_input={'is_terminal': True})

    assert run_result_2.status == 'SUCCEEDED'
    assert run_result_2.status_message == 'testing-status-message'
    assert run_result_2.is_status_message_terminal is True


async def test_actor_starts_another_actor_instance(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main_inner() -> None:
        async with Actor:
            await asyncio.sleep(5)
            actor_input = await Actor.get_input() or {}
            test_value = actor_input.get('test_value')
            await Actor.set_value('OUTPUT', f'{test_value}_XXX_{test_value}')

    async def main_outer() -> None:
        async with Actor:
            actor_input = await Actor.get_input() or {}
            inner_actor_id = actor_input.get('inner_actor_id')
            test_value = actor_input.get('test_value')

            assert inner_actor_id is not None

            await Actor.start(inner_actor_id, run_input={'test_value': test_value})

            inner_run_status = await Actor.apify_client.actor(inner_actor_id).last_run().get()
            assert inner_run_status is not None
            assert inner_run_status.get('status') in ['READY', 'RUNNING']

    inner_actor = await make_actor(label='start-inner', main_func=main_inner)
    outer_actor = await make_actor(label='start-outer', main_func=main_outer)

    inner_actor_id = (await inner_actor.get() or {})['id']
    test_value = crypto_random_object_id()

    run_result_outer = await run_actor(
        outer_actor,
        run_input={'test_value': test_value, 'inner_actor_id': inner_actor_id},
    )

    assert run_result_outer.status == 'SUCCEEDED'

    await inner_actor.last_run().wait_for_finish(wait_secs=600)

    inner_output_record = await inner_actor.last_run().key_value_store().get_record('OUTPUT')
    assert inner_output_record is not None
    assert inner_output_record['value'] == f'{test_value}_XXX_{test_value}'


async def test_actor_calls_another_actor(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main_inner() -> None:
        async with Actor:
            await asyncio.sleep(5)
            actor_input = await Actor.get_input() or {}
            test_value = actor_input.get('test_value')
            await Actor.set_value('OUTPUT', f'{test_value}_XXX_{test_value}')

    async def main_outer() -> None:
        async with Actor:
            actor_input = await Actor.get_input() or {}
            inner_actor_id = actor_input.get('inner_actor_id')
            test_value = actor_input.get('test_value')

            assert inner_actor_id is not None

            await Actor.call(inner_actor_id, run_input={'test_value': test_value})

            inner_run_status = await Actor.apify_client.actor(inner_actor_id).last_run().get()
            assert inner_run_status is not None
            assert inner_run_status.get('status') == 'SUCCEEDED'

    inner_actor = await make_actor(label='call-inner', main_func=main_inner)
    outer_actor = await make_actor(label='call-outer', main_func=main_outer)

    inner_actor_id = (await inner_actor.get() or {})['id']
    test_value = crypto_random_object_id()

    run_result_outer = await run_actor(
        outer_actor,
        run_input={'test_value': test_value, 'inner_actor_id': inner_actor_id},
    )

    assert run_result_outer.status == 'SUCCEEDED'

    await inner_actor.last_run().wait_for_finish(wait_secs=600)

    inner_output_record = await inner_actor.last_run().key_value_store().get_record('OUTPUT')
    assert inner_output_record is not None
    assert inner_output_record['value'] == f'{test_value}_XXX_{test_value}'


async def test_actor_calls_task(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
    apify_client_async: ApifyClientAsync,
) -> None:
    async def main_inner() -> None:
        async with Actor:
            await asyncio.sleep(5)
            actor_input = await Actor.get_input() or {}
            test_value = actor_input.get('test_value')
            await Actor.set_value('OUTPUT', f'{test_value}_XXX_{test_value}')

    async def main_outer() -> None:
        async with Actor:
            actor_input = await Actor.get_input() or {}
            inner_task_id = actor_input.get('inner_task_id')

            assert inner_task_id is not None

            await Actor.call_task(inner_task_id)

            inner_run_status = await Actor.apify_client.task(inner_task_id).last_run().get()
            assert inner_run_status is not None
            assert inner_run_status.get('status') == 'SUCCEEDED'

    inner_actor = await make_actor(label='call-task-inner', main_func=main_inner)
    outer_actor = await make_actor(label='call-task-outer', main_func=main_outer)

    inner_actor_id = (await inner_actor.get() or {})['id']
    test_value = crypto_random_object_id()

    task = await apify_client_async.tasks().create(
        actor_id=inner_actor_id,
        name=generate_unique_resource_name('actor-call-task'),
        task_input={'test_value': test_value},
    )

    run_result_outer = await run_actor(
        outer_actor,
        run_input={'test_value': test_value, 'inner_task_id': task['id']},
    )

    assert run_result_outer.status == 'SUCCEEDED'

    await inner_actor.last_run().wait_for_finish(wait_secs=600)

    inner_output_record = await inner_actor.last_run().key_value_store().get_record('OUTPUT')
    assert inner_output_record is not None
    assert inner_output_record['value'] == f'{test_value}_XXX_{test_value}'

    await apify_client_async.task(task['id']).delete()


async def test_actor_aborts_another_actor_run(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main_inner() -> None:
        async with Actor:
            await asyncio.sleep(180)
            # This should not be set, the actor should be aborted by now
            await Actor.set_value('OUTPUT', 'dummy')

    async def main_outer() -> None:
        async with Actor:
            actor_input = await Actor.get_input() or {}
            inner_run_id = actor_input.get('inner_run_id')

            assert inner_run_id is not None

            await Actor.abort(inner_run_id)

    inner_actor = await make_actor(label='abort-inner', main_func=main_inner)
    outer_actor = await make_actor(label='abort-outer', main_func=main_outer)

    inner_run_id = (await inner_actor.start())['id']

    run_result_outer = await run_actor(
        outer_actor,
        run_input={'inner_run_id': inner_run_id},
    )

    assert run_result_outer.status == 'SUCCEEDED'

    await inner_actor.last_run().wait_for_finish(wait_secs=600)
    inner_actor_last_run_dict = await inner_actor.last_run().get()
    inner_actor_last_run = ActorRun.model_validate(inner_actor_last_run_dict)

    assert inner_actor_last_run.status == 'ABORTED'

    inner_output_record = await inner_actor.last_run().key_value_store().get_record('OUTPUT')
    assert inner_output_record is None


async def test_actor_metamorphs_into_another_actor(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main_inner() -> None:
        import os

        from apify_shared.consts import ActorEnvVars

        async with Actor:
            assert os.getenv(ActorEnvVars.INPUT_KEY) is not None
            assert os.getenv(ActorEnvVars.INPUT_KEY) != 'INPUT'
            actor_input = await Actor.get_input() or {}

            test_value = actor_input.get('test_value', '')
            assert test_value.endswith('_BEFORE_METAMORPH')

            output = test_value.replace('_BEFORE_METAMORPH', '_AFTER_METAMORPH')
            await Actor.set_value('OUTPUT', output)

    async def main_outer() -> None:
        async with Actor:
            actor_input = await Actor.get_input() or {}
            inner_actor_id = actor_input.get('inner_actor_id')
            test_value = actor_input.get('test_value')
            new_test_value = f'{test_value}_BEFORE_METAMORPH'

            assert inner_actor_id is not None

            await Actor.metamorph(inner_actor_id, run_input={'test_value': new_test_value})

            # This should not be called
            await Actor.set_value('RECORD_AFTER_METAMORPH_CALL', 'dummy')
            raise AssertionError('The Actor should have been metamorphed by now')

    inner_actor = await make_actor(label='metamorph-inner', main_func=main_inner)
    outer_actor = await make_actor(label='metamorph-outer', main_func=main_outer)

    inner_actor_id = (await inner_actor.get() or {})['id']
    test_value = crypto_random_object_id()

    run_result_outer = await run_actor(
        outer_actor,
        run_input={'test_value': test_value, 'inner_actor_id': inner_actor_id},
    )

    assert run_result_outer.status == 'SUCCEEDED'

    outer_run_key_value_store = outer_actor.last_run().key_value_store()

    outer_output_record = await outer_run_key_value_store.get_record('OUTPUT')
    assert outer_output_record is not None
    assert outer_output_record['value'] == f'{test_value}_AFTER_METAMORPH'

    assert await outer_run_key_value_store.get_record('RECORD_AFTER_METAMORPH_CALL') is None

    # After metamorph, the run still belongs to the original Actor, so the inner one should have no runs
    assert await inner_actor.last_run().get() is None


async def test_actor_reboots_successfully(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        async with Actor:
            print('Starting...')
            cnt = await Actor.get_value('reboot_counter', 0)

            if cnt < 2:
                print(f'Rebooting (cnt = {cnt})...')
                await Actor.set_value('reboot_counter', cnt + 1)
                await Actor.reboot()
                await Actor.set_value('THIS_KEY_SHOULD_NOT_BE_WRITTEN', 'XXX')

            print('Finishing...')

    actor = await make_actor(label='actor_rebooter', main_func=main)

    run_result = await run_actor(
        actor,
        run_input={'counter_key': 'reboot_counter'},
    )

    assert run_result.status == 'SUCCEEDED'

    not_written_value = await actor.last_run().key_value_store().get_record('THIS_KEY_SHOULD_NOT_BE_WRITTEN')
    assert not_written_value is None

    reboot_counter = await actor.last_run().key_value_store().get_record('reboot_counter')
    assert reboot_counter is not None
    assert reboot_counter['value'] == 2


async def test_actor_adds_webhook_and_receives_event(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main_server() -> None:
        import os
        from http.server import BaseHTTPRequestHandler, HTTPServer

        from apify_shared.consts import ActorEnvVars

        webhook_body = ''

        async with Actor:

            class WebhookHandler(BaseHTTPRequestHandler):
                def do_GET(self) -> None:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(bytes('Hello, world!', encoding='utf-8'))

                def do_POST(self) -> None:
                    nonlocal webhook_body
                    content_length = self.headers.get('content-length')
                    length = int(content_length) if content_length else 0
                    webhook_body = self.rfile.read(length).decode('utf-8')
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(bytes('Hello, world!', encoding='utf-8'))

            container_port = int(os.getenv(ActorEnvVars.WEB_SERVER_PORT, ''))
            with HTTPServer(('', container_port), WebhookHandler) as server:
                await Actor.set_value('INITIALIZED', value=True)
                while not webhook_body:
                    server.handle_request()

            await Actor.set_value('WEBHOOK_BODY', webhook_body)

    async def main_client() -> None:
        from apify import Webhook, WebhookEventType

        async with Actor:
            actor_input = await Actor.get_input() or {}
            server_actor_container_url = str(actor_input.get('server_actor_container_url'))

            await Actor.add_webhook(
                Webhook(
                    event_types=[WebhookEventType.ACTOR_RUN_SUCCEEDED],
                    request_url=server_actor_container_url,
                )
            )

    server_actor, client_actor = await asyncio.gather(
        make_actor(label='add-webhook-server', main_func=main_server),
        make_actor(label='add-webhook-client', main_func=main_client),
    )

    server_actor_run = await server_actor.start()
    server_actor_container_url = server_actor_run['containerUrl']

    server_actor_initialized = await server_actor.last_run().key_value_store().get_record('INITIALIZED')
    while not server_actor_initialized:
        server_actor_initialized = await server_actor.last_run().key_value_store().get_record('INITIALIZED')
        await asyncio.sleep(1)

    ac_run_result = await run_actor(
        client_actor,
        run_input={'server_actor_container_url': server_actor_container_url},
    )

    assert ac_run_result.status == 'SUCCEEDED'

    sa_run_result_dict = await server_actor.last_run().wait_for_finish(wait_secs=600)
    sa_run_result = ActorRun.model_validate(sa_run_result_dict)

    assert sa_run_result.status == 'SUCCEEDED'

    webhook_body_record = await server_actor.last_run().key_value_store().get_record('WEBHOOK_BODY')
    assert webhook_body_record is not None
    assert webhook_body_record['value'] != ''
    parsed_webhook_body = json.loads(webhook_body_record['value'])

    assert parsed_webhook_body['eventData']['actorId'] == ac_run_result.act_id
    assert parsed_webhook_body['eventData']['actorRunId'] == ac_run_result.id
