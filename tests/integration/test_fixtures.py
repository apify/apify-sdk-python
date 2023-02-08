from datetime import datetime, timezone

from apify import Actor
from apify._crypto import _crypto_random_object_id
from apify_client import ApifyClientAsync

from .conftest import ActorFactory


class TestMakeActorFixture:
    async def test_main_func(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            import os

            from apify.consts import ApifyEnvVars

            async with Actor:
                await Actor.set_value('OUTPUT', os.getenv(ApifyEnvVars.ACTOR_ID))

        actor = await make_actor('make-actor-main-func', main_func=main)

        run_result = await actor.call()

        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'

        output_record = await actor.last_run().key_value_store().get_record('OUTPUT')
        assert output_record is not None
        assert run_result['actId'] == output_record['value']

    async def test_main_py(self, make_actor: ActorFactory) -> None:
        expected_output = f'ACTOR_OUTPUT_{_crypto_random_object_id(5)}'
        main_py_source = f"""
            import asyncio
            from apify import Actor
            async def main():
                async with Actor:
                    await Actor.set_value('OUTPUT', '{expected_output}')
        """

        actor = await make_actor('make-actor-main-py', main_py=main_py_source)

        run_result = await actor.call()
        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'

        output_record = await actor.last_run().key_value_store().get_record('OUTPUT')
        assert output_record is not None
        assert output_record['value'] == expected_output

    async def test_source_files(self, make_actor: ActorFactory) -> None:
        test_started_at = datetime.now(timezone.utc)
        actor_source_files = {
            'src/utils.py': """
                from datetime import datetime

                def get_current_datetime():
                    return datetime.now(timezone.utc)
            """,
            'src/main.py': """
                import asyncio
                from apify import Actor
                from .utils import get_current_datetime

                async def main():
                    async with Actor:
                        current_datetime = get_current_datetime()
                        await Actor.set_value('OUTPUT', current_datetime)
            """,
        }
        actor = await make_actor('make-actor-source-files', source_files=actor_source_files)

        actor_run = await actor.call()
        assert actor_run is not None
        assert actor_run['status'] == 'SUCCEEDED'

        output_record = await actor.last_run().key_value_store().get_record('OUTPUT')
        assert output_record is not None

        output_datetime = datetime.fromisoformat(output_record['value'])
        assert output_datetime > test_started_at
        assert output_datetime < datetime.now(timezone.utc)


class TestApifyClientAsyncFixture:
    async def test_apify_client_async_works(self, apify_client_async: ApifyClientAsync) -> None:
        assert await apify_client_async.user('me').get() is not None
