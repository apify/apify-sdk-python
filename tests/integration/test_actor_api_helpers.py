import asyncio
import json

from apify import Actor
from apify._crypto import _crypto_random_object_id
from apify_client import ApifyClientAsync

from ._utils import generate_unique_resource_name
from .conftest import ActorFactory


class TestActorIsAtHome:
    async def test_actor_is_at_home(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            async with Actor:
                assert Actor.is_at_home() is True

        actor = await make_actor('is-at-home', main_func=main)

        run_result = await actor.call()

        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'


class TestActorGetEnv:
    async def test_actor_get_env(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            async with Actor:
                env_dict = Actor.get_env()

                assert env_dict.get('is_at_home') is True
                assert env_dict.get('token') is not None
                assert env_dict.get('actor_events_ws_url') is not None
                assert env_dict.get('input_key') is not None

                assert len(env_dict.get('actor_id', '')) == 17
                assert len(env_dict.get('actor_run_id', '')) == 17
                assert len(env_dict.get('user_id', '')) == 17
                assert len(env_dict.get('default_dataset_id', '')) == 17
                assert len(env_dict.get('default_key_value_store_id', '')) == 17
                assert len(env_dict.get('default_request_queue_id', '')) == 17

        actor = await make_actor('get-env', main_func=main)

        run_result = await actor.call()

        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'


class TestActorNewClient:
    async def test_actor_new_client(self, make_actor: ActorFactory) -> None:
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

        actor = await make_actor('new-client', main_func=main)

        run_result = await actor.call()

        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'

        output_record = await actor.last_run().key_value_store().get_record('OUTPUT')
        assert output_record is not None
        assert output_record['value'] == 'TESTING-OUTPUT'


class TestActorSetStatusMessage:
    async def test_actor_set_status_message(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            async with Actor:
                input = await Actor.get_input() or {}
                await Actor.set_status_message('testing-status-message', **input)

        actor = await make_actor('set-status-message', main_func=main)

        run_result = await actor.call()

        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'
        assert run_result['statusMessage'] == 'testing-status-message'
        assert run_result['isStatusMessageTerminal'] is None

        run_result = await actor.call(run_input={'is_terminal': True})

        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'
        assert run_result['statusMessage'] == 'testing-status-message'
        assert run_result['isStatusMessageTerminal'] is True


class TestActorStart:
    async def test_actor_start(self, make_actor: ActorFactory) -> None:
        async def main_inner() -> None:
            async with Actor:
                await asyncio.sleep(5)
                input = await Actor.get_input() or {}
                test_value = input.get('test_value')
                await Actor.set_value('OUTPUT', f'{test_value}_XXX_{test_value}')

        async def main_outer() -> None:
            async with Actor:
                input = await Actor.get_input() or {}
                inner_actor_id = input.get('inner_actor_id')
                test_value = input.get('test_value')

                assert inner_actor_id is not None

                await Actor.start(inner_actor_id, run_input={'test_value': test_value})

                inner_run_status = await Actor.apify_client.actor(inner_actor_id).last_run().get()
                assert inner_run_status is not None
                assert inner_run_status.get('status') in ['READY', 'RUNNING']

        inner_actor = await make_actor('start-inner', main_func=main_inner)
        outer_actor = await make_actor('start-outer', main_func=main_outer)

        inner_actor_id = (await inner_actor.get() or {})['id']
        test_value = _crypto_random_object_id()

        outer_run_result = await outer_actor.call(run_input={'test_value': test_value, 'inner_actor_id': inner_actor_id})

        assert outer_run_result is not None
        assert outer_run_result['status'] == 'SUCCEEDED'

        await inner_actor.last_run().wait_for_finish()

        inner_output_record = await inner_actor.last_run().key_value_store().get_record('OUTPUT')
        assert inner_output_record is not None
        assert inner_output_record['value'] == f'{test_value}_XXX_{test_value}'


class TestActorCall:
    async def test_actor_call(self, make_actor: ActorFactory) -> None:
        async def main_inner() -> None:
            async with Actor:
                await asyncio.sleep(5)
                input = await Actor.get_input() or {}
                test_value = input.get('test_value')
                await Actor.set_value('OUTPUT', f'{test_value}_XXX_{test_value}')

        async def main_outer() -> None:
            async with Actor:
                input = await Actor.get_input() or {}
                inner_actor_id = input.get('inner_actor_id')
                test_value = input.get('test_value')

                assert inner_actor_id is not None

                await Actor.call(inner_actor_id, run_input={'test_value': test_value})

                inner_run_status = await Actor.apify_client.actor(inner_actor_id).last_run().get()
                assert inner_run_status is not None
                assert inner_run_status.get('status') == 'SUCCEEDED'

        inner_actor = await make_actor('call-inner', main_func=main_inner)
        outer_actor = await make_actor('call-outer', main_func=main_outer)

        inner_actor_id = (await inner_actor.get() or {})['id']
        test_value = _crypto_random_object_id()

        outer_run_result = await outer_actor.call(run_input={'test_value': test_value, 'inner_actor_id': inner_actor_id})

        assert outer_run_result is not None
        assert outer_run_result['status'] == 'SUCCEEDED'

        await inner_actor.last_run().wait_for_finish()

        inner_output_record = await inner_actor.last_run().key_value_store().get_record('OUTPUT')
        assert inner_output_record is not None
        assert inner_output_record['value'] == f'{test_value}_XXX_{test_value}'


class TestActorCallTask:
    async def test_actor_call_task(self, make_actor: ActorFactory, apify_client_async: ApifyClientAsync) -> None:
        async def main_inner() -> None:
            async with Actor:
                await asyncio.sleep(5)
                input = await Actor.get_input() or {}
                test_value = input.get('test_value')
                await Actor.set_value('OUTPUT', f'{test_value}_XXX_{test_value}')

        async def main_outer() -> None:
            async with Actor:
                input = await Actor.get_input() or {}
                inner_task_id = input.get('inner_task_id')

                assert inner_task_id is not None

                await Actor.call_task(inner_task_id)

                inner_run_status = await Actor.apify_client.task(inner_task_id).last_run().get()
                assert inner_run_status is not None
                assert inner_run_status.get('status') == 'SUCCEEDED'

        inner_actor = await make_actor('call-task-inner', main_func=main_inner)
        outer_actor = await make_actor('call-task-outer', main_func=main_outer)

        inner_actor_id = (await inner_actor.get() or {})['id']
        test_value = _crypto_random_object_id()

        task = await apify_client_async.tasks().create(
            actor_id=inner_actor_id,
            name=generate_unique_resource_name('actor-call-task'),
            task_input={'test_value': test_value},
        )

        outer_run_result = await outer_actor.call(run_input={'test_value': test_value, 'inner_task_id': task['id']})

        assert outer_run_result is not None
        assert outer_run_result['status'] == 'SUCCEEDED'

        await inner_actor.last_run().wait_for_finish()

        inner_output_record = await inner_actor.last_run().key_value_store().get_record('OUTPUT')
        assert inner_output_record is not None
        assert inner_output_record['value'] == f'{test_value}_XXX_{test_value}'

        await apify_client_async.task(task['id']).delete()


class TestActorAbort:
    async def test_actor_abort(self, make_actor: ActorFactory) -> None:
        async def main_inner() -> None:
            async with Actor:
                await asyncio.sleep(180)
                # This should not be set, the actor should be aborted by now
                await Actor.set_value('OUTPUT', 'dummy')

        async def main_outer() -> None:
            async with Actor:
                input = await Actor.get_input() or {}
                inner_run_id = input.get('inner_run_id')

                assert inner_run_id is not None

                await Actor.abort(inner_run_id)

        inner_actor = await make_actor('abort-inner', main_func=main_inner)
        outer_actor = await make_actor('abort-outer', main_func=main_outer)

        inner_run_id = (await inner_actor.start())['id']

        outer_run_result = await outer_actor.call(run_input={'inner_run_id': inner_run_id})

        assert outer_run_result is not None
        assert outer_run_result['status'] == 'SUCCEEDED'

        await inner_actor.last_run().wait_for_finish()
        inner_actor_last_run = await inner_actor.last_run().get()
        assert inner_actor_last_run is not None
        assert inner_actor_last_run['status'] == 'ABORTED'

        inner_output_record = await inner_actor.last_run().key_value_store().get_record('OUTPUT')
        assert inner_output_record is None


class TestActorMetamorph:
    async def test_actor_metamorph(self, make_actor: ActorFactory) -> None:
        async def main_inner() -> None:
            import os

            from apify_shared.consts import ActorEnvVars

            async with Actor:
                assert os.getenv(ActorEnvVars.INPUT_KEY) is not None
                assert os.getenv(ActorEnvVars.INPUT_KEY) != 'INPUT'
                input = await Actor.get_input() or {}

                test_value = input.get('test_value', '')
                assert test_value.endswith('_BEFORE_METAMORPH')

                output = test_value.replace('_BEFORE_METAMORPH', '_AFTER_METAMORPH')
                await Actor.set_value('OUTPUT', output)

        async def main_outer() -> None:
            async with Actor:
                input = await Actor.get_input() or {}
                inner_actor_id = input.get('inner_actor_id')
                test_value = input.get('test_value')
                new_test_value = f'{test_value}_BEFORE_METAMORPH'

                assert inner_actor_id is not None

                await Actor.metamorph(inner_actor_id, run_input={'test_value': new_test_value})

                # This should not be called
                await Actor.set_value('RECORD_AFTER_METAMORPH_CALL', 'dummy')
                raise AssertionError('The actor should have been metamorphed by now')

        inner_actor = await make_actor('metamorph-inner', main_func=main_inner)
        outer_actor = await make_actor('metamorph-outer', main_func=main_outer)

        inner_actor_id = (await inner_actor.get() or {})['id']
        test_value = _crypto_random_object_id()

        outer_run_result = await outer_actor.call(run_input={'test_value': test_value, 'inner_actor_id': inner_actor_id})

        assert outer_run_result is not None
        assert outer_run_result['status'] == 'SUCCEEDED'

        outer_run_key_value_store = outer_actor.last_run().key_value_store()

        outer_output_record = await outer_run_key_value_store.get_record('OUTPUT')
        assert outer_output_record is not None
        assert outer_output_record['value'] == f'{test_value}_AFTER_METAMORPH'

        assert await outer_run_key_value_store.get_record('RECORD_AFTER_METAMORPH_CALL') is None

        # After metamorph, the run still belongs to the original actor, so the inner one should have no runs
        assert await inner_actor.last_run().get() is None


class TestActorAddWebhook:
    async def test_actor_add_webhook(self, make_actor: ActorFactory) -> None:
        async def main_server() -> None:
            import os
            from http.server import BaseHTTPRequestHandler, HTTPServer

            from apify_shared.consts import ActorEnvVars

            webhook_body = ''

            async with Actor:
                class WebhookHandler(BaseHTTPRequestHandler):
                    def do_GET(self) -> None:  # noqa: N802
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(bytes('Hello, world!', encoding='utf-8'))

                    def do_POST(self) -> None:  # noqa: N802
                        nonlocal webhook_body
                        content_length = self.headers.get('content-length')
                        length = int(content_length) if content_length else 0

                        webhook_body = self.rfile.read(length).decode('utf-8')

                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(bytes('Hello, world!', encoding='utf-8'))

                container_port = int(os.getenv(ActorEnvVars.WEB_SERVER_PORT, ''))
                with HTTPServer(('', container_port), WebhookHandler) as server:
                    await Actor.set_value('INITIALIZED', True)
                    while not webhook_body:
                        server.handle_request()

                await Actor.set_value('WEBHOOK_BODY', webhook_body)

        async def main_client() -> None:
            from apify_shared.consts import WebhookEventType
            async with Actor:
                input = await Actor.get_input() or {}
                server_actor_container_url = str(input.get('server_actor_container_url'))

                await Actor.add_webhook(
                    event_types=[WebhookEventType.ACTOR_RUN_SUCCEEDED],
                    request_url=server_actor_container_url,
                )

        server_actor, client_actor = await asyncio.gather(
            make_actor('add-webhook-server', main_func=main_server),
            make_actor('add-webhook-client', main_func=main_client),
        )

        server_actor_run = await server_actor.start()
        server_actor_container_url = server_actor_run['containerUrl']

        # Give the server actor some time to start running
        server_actor_initialized = await server_actor.last_run().key_value_store().get_record('INITIALIZED')
        while not server_actor_initialized:
            server_actor_initialized = await server_actor.last_run().key_value_store().get_record('INITIALIZED')
            await asyncio.sleep(1)

        client_actor_run_result = await client_actor.call(run_input={'server_actor_container_url': server_actor_container_url})
        assert client_actor_run_result is not None
        assert client_actor_run_result['status'] == 'SUCCEEDED'

        server_actor_run_result = await server_actor.last_run().wait_for_finish()
        assert server_actor_run_result is not None
        assert server_actor_run_result['status'] == 'SUCCEEDED'

        webhook_body_record = await server_actor.last_run().key_value_store().get_record('WEBHOOK_BODY')
        assert webhook_body_record is not None
        assert webhook_body_record['value'] != ''
        parsed_webhook_body = json.loads(webhook_body_record['value'])

        assert parsed_webhook_body['eventData']['actorId'] == client_actor_run_result['actId']
        assert parsed_webhook_body['eventData']['actorRunId'] == client_actor_run_result['id']
