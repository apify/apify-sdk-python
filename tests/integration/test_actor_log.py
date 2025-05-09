from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from apify import Actor, __version__
from ._utils import generate_unique_resource_name

if TYPE_CHECKING:
    from .conftest import MakeActorFunction, RunActorFunction


# TODO: What to do with the `browserforge` output?
# https://github.com/apify/apify-sdk-python/issues/423
@pytest.mark.skip
async def test_actor_logging(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        import logging

        from apify.log import logger

        async with Actor:
            logger.setLevel(logging.DEBUG)

            # Test Actor.log
            Actor.log.debug('Debug message')
            Actor.log.info('Info message')

            # Test logger
            logger.warning('Warning message')
            logger.error('Error message')

            # Test that exception is logged with the traceback
            try:
                raise ValueError('Dummy ValueError')
            except Exception:
                Actor.log.exception('Exception message')

            # Test multiline message being indented correctly
            logger.info('Multi\nline\nlog\nmessage')

            # Test that exception in Actor.main is logged with the traceback
            raise RuntimeError('Dummy RuntimeError')

    actor = await make_actor(label='actor-log', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'FAILED'

    run_log = await actor.last_run().log().get()
    assert run_log is not None

    run_log_lines = run_log.splitlines()

    # This should prevent issues when the test run is migrated, and it would have its log restarted
    expected_log_lines_count = 24
    assert len(run_log_lines) >= expected_log_lines_count
    run_log_lines = run_log_lines[-expected_log_lines_count:]

    # This removes the datetime from the start of log lines
    run_log_lines = [line[25:] for line in run_log_lines]

    # This might be way too specific and easy to break, but let's hope not
    assert run_log_lines.pop(0).startswith('ACTOR: Pulling Docker image')
    assert run_log_lines.pop(0) == 'ACTOR: Creating Docker container.'
    assert run_log_lines.pop(0) == 'ACTOR: Starting Docker container.'
    assert run_log_lines.pop(0) == '[apify] INFO  Initializing Actor...'
    assert run_log_lines.pop(0).startswith(
        f'[apify] INFO  System info ({{"apify_sdk_version": "{__version__}", "apify_client_version": "'
    )
    assert run_log_lines.pop(0) == '[apify] DEBUG Debug message'
    assert run_log_lines.pop(0) == '[apify] INFO  Info message'
    assert run_log_lines.pop(0) == '[apify] WARN  Warning message'
    assert run_log_lines.pop(0) == '[apify] ERROR Error message'
    assert run_log_lines.pop(0) == '[apify] ERROR Exception message'
    assert run_log_lines.pop(0) == '      Traceback (most recent call last):'
    assert run_log_lines.pop(0) == '        File "/usr/src/app/src/main.py", line 25, in main'
    assert run_log_lines.pop(0) == "          raise ValueError('Dummy ValueError')"
    assert run_log_lines.pop(0) == '      ValueError: Dummy ValueError'
    assert run_log_lines.pop(0) == '[apify] INFO  Multi'
    assert run_log_lines.pop(0) == 'line'
    assert run_log_lines.pop(0) == 'log'
    assert run_log_lines.pop(0) == 'message'
    assert run_log_lines.pop(0) == '[apify] ERROR Actor failed with an exception'
    assert run_log_lines.pop(0) == '      Traceback (most recent call last):'
    assert run_log_lines.pop(0) == '        File "/usr/src/app/src/main.py", line 33, in main'
    assert run_log_lines.pop(0) == "          raise RuntimeError('Dummy RuntimeError')"
    assert run_log_lines.pop(0) == '      RuntimeError: Dummy RuntimeError'
    assert run_log_lines.pop(0) == '[apify] INFO  Exiting Actor ({"exit_code": 91})'


async def test_actor_redirected_logs(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test that one actor that starts another actor can redirect logs correctly."""

    async def main_second() -> None:
        # Second actor from which we want to redirect logs
        import logging

        from apify.log import logger

        async with Actor:
            # Test Actor.log
            Actor.log.info('Info message')
            Actor.log.warning('Warning message')
            Actor.log.error('Error message')

            # Test that exception is logged with the traceback
            try:
                raise ValueError('Dummy ValueError')
            except Exception:
                Actor.log.exception('Exception message')

            # Test that exception in Actor.main is logged with the traceback
            raise RuntimeError('Dummy RuntimeError')

    actor_id = (await make_actor(label='actor-log', main_func=main_second))["id"]

    async def main_top() -> None:
        # Top actor that will start the second actor and will get its redirected logs
        async with Actor:
            # Start the second actor
            run = Actor.start(actor_id)
            Actor.redirect_log(run["id"])

    actor = await make_actor(label='actor-log', main_func=main_top, dynamic_code= f"actor_id={actor_id}")

    run_result = await run_actor(actor)
    print("a")
