from __future__ import annotations

from typing import TYPE_CHECKING

from apify import Actor

if TYPE_CHECKING:
    from .conftest import MakeActorFunction, RunActorFunction


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

    # Remove the datetime from the start of log lines
    run_log_lines = [line[25:] for line in run_log_lines]

    # Join all lines to make it easier to search for expected content
    full_log = '\n'.join(run_log_lines)

    # Verify expected log messages are present (order-independent checks)
    assert '[apify] DEBUG Debug message' in full_log
    assert '[apify] INFO  Info message' in full_log
    assert '[apify] WARN  Warning message' in full_log
    assert '[apify] ERROR Error message' in full_log
    assert '[apify] ERROR Exception message' in full_log
    assert 'ValueError: Dummy ValueError' in full_log
    assert '[apify] INFO  Multi' in full_log
    assert '[apify] ERROR Actor failed with an exception' in full_log
    assert 'RuntimeError: Dummy RuntimeError' in full_log

    # Verify multiline log message is present
    assert 'line\nlog\nmessage' in full_log or ('line' in full_log and 'log' in full_log and 'message' in full_log)

    # Verify exit message is present
    assert '[apify] INFO  Exiting Actor ({"exit_code": 91})' in full_log
