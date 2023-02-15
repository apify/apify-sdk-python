from apify import Actor, __version__
from apify_client._version import __version__ as apify_client_version

from .conftest import ActorFactory


class TestActorLog:
    async def test_actor_log(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            import logging

            from apify.log import ActorLogFormatter, logger

            # Clear any other log handlers, so they don't mess with this test
            client_logger = logging.getLogger('apify_client')
            apify_logger = logging.getLogger('apify')
            client_logger.handlers.clear()
            apify_logger.handlers.clear()

            # Set handler only on the 'apify' logger
            apify_logger.setLevel(logging.DEBUG)
            handler = logging.StreamHandler()
            handler.setFormatter(ActorLogFormatter())
            apify_logger.addHandler(handler)

            async with Actor:
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

        actor = await make_actor('actor-log', main_func=main)

        run_result = await actor.call()

        assert run_result is not None
        assert run_result['status'] == 'FAILED'

        run_log = await actor.last_run().log().get()
        assert run_log is not None

        run_log_lines = run_log.splitlines()

        # This should prevent issues when the test run is migrated, and it would have its log restarted
        expected_log_lines_count = 24
        assert len(run_log_lines) >= expected_log_lines_count
        run_log_lines = run_log_lines[-expected_log_lines_count:]

        # This removes the datetime from the start of log lines
        run_log_lines = list(map(lambda line: line[25:], run_log_lines))

        # This might be way too specific and easy to break, but let's hope not
        assert run_log_lines.pop(0) == 'ACTOR: Pulling Docker image from repository.'
        assert run_log_lines.pop(0) == 'ACTOR: Creating Docker container.'
        assert run_log_lines.pop(0) == 'ACTOR: Starting Docker container.'
        assert run_log_lines.pop(0) == 'INFO  Initializing actor...'
        assert run_log_lines.pop(0).startswith(f'INFO  System info ({{"apify_sdk_version": "{__version__}", "apify_client_version": "{apify_client_version}"')  # noqa: E501
        assert run_log_lines.pop(0) == 'DEBUG Debug message'
        assert run_log_lines.pop(0) == 'INFO  Info message'
        assert run_log_lines.pop(0) == 'WARN  Warning message'
        assert run_log_lines.pop(0) == 'ERROR Error message'
        assert run_log_lines.pop(0) == 'ERROR Exception message'
        assert run_log_lines.pop(0) == '      Traceback (most recent call last):'
        assert run_log_lines.pop(0) == '        File "/usr/src/app/src/main.py", line 34, in main'
        assert run_log_lines.pop(0) == "          raise ValueError('Dummy ValueError')"
        assert run_log_lines.pop(0) == '      ValueError: Dummy ValueError'
        assert run_log_lines.pop(0) == 'INFO  Multi'
        assert run_log_lines.pop(0) == '      line'
        assert run_log_lines.pop(0) == '      log'
        assert run_log_lines.pop(0) == '      message'
        assert run_log_lines.pop(0) == 'ERROR Actor failed with an exception'
        assert run_log_lines.pop(0) == '      Traceback (most recent call last):'
        assert run_log_lines.pop(0) == '        File "/usr/src/app/src/main.py", line 42, in main'
        assert run_log_lines.pop(0) == "          raise RuntimeError('Dummy RuntimeError')"
        assert run_log_lines.pop(0) == '      RuntimeError: Dummy RuntimeError'
        assert run_log_lines.pop(0) == 'INFO  Exiting actor ({"exit_code": 91})'
