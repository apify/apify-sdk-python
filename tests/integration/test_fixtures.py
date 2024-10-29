from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from crawlee._utils.crypto import crypto_random_object_id

from apify import Actor

if TYPE_CHECKING:
    from apify_client import ApifyClientAsync

    from .conftest import ActorFactory


async def test_actor_from_main_func(
    apify_client_async: ApifyClientAsync,
    make_actor: ActorFactory,
) -> None:
    async def main() -> None:
        import os

        from apify_shared.consts import ActorEnvVars

        async with Actor:
            await Actor.set_value('OUTPUT', os.getenv(ActorEnvVars.ID))

    actor = await make_actor('make-actor-main-func', main_func=main)

    call_result = await actor.call()
    assert call_result is not None

    run_client = apify_client_async.run(call_result['id'])
    run_result = await run_client.wait_for_finish(wait_secs=300)

    assert run_result is not None
    assert run_result['status'] == 'SUCCEEDED'

    output_record = await actor.last_run().key_value_store().get_record('OUTPUT')
    assert output_record is not None
    assert run_result['actId'] == output_record['value']


async def test_actor_from_main_py(
    apify_client_async: ApifyClientAsync,
    make_actor: ActorFactory,
) -> None:
    expected_output = f'ACTOR_OUTPUT_{crypto_random_object_id(5)}'
    main_py_source = f"""
        import asyncio
        from apify import Actor
        async def main():
            async with Actor:
                await Actor.set_value('OUTPUT', '{expected_output}')
    """

    actor = await make_actor('make-actor-main-py', main_py=main_py_source)

    call_result = await actor.call()
    assert call_result is not None

    run_client = apify_client_async.run(call_result['id'])
    run_result = await run_client.wait_for_finish(wait_secs=300)

    assert run_result is not None
    assert run_result['status'] == 'SUCCEEDED'

    output_record = await actor.last_run().key_value_store().get_record('OUTPUT')
    assert output_record is not None
    assert output_record['value'] == expected_output


async def test_actor_from_source_files(
    apify_client_async: ApifyClientAsync,
    make_actor: ActorFactory,
) -> None:
    test_started_at = datetime.now(timezone.utc)
    actor_source_files = {
        'src/utils.py': """
            from datetime import datetime, timezone

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

    call_result = await actor.call()
    assert call_result is not None

    run_client = apify_client_async.run(call_result['id'])
    run_result = await run_client.wait_for_finish(wait_secs=300)

    assert run_result is not None
    assert run_result['status'] == 'SUCCEEDED'

    output_record = await actor.last_run().key_value_store().get_record('OUTPUT')
    assert output_record is not None

    output_datetime = datetime.fromisoformat(output_record['value'])
    assert output_datetime > test_started_at
    assert output_datetime < datetime.now(timezone.utc)


async def test_apify_client_async_works(apify_client_async: ApifyClientAsync) -> None:
    assert await apify_client_async.user('me').get() is not None
