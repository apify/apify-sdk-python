from __future__ import annotations

import contextlib
import logging

import pytest

from apify import Actor
from apify.log import logger


@pytest.mark.skip(reason='There are issues with log propagation to caplog, see issue #462.')
async def test_actor_logs_messages_correctly(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger='apify')

    with contextlib.suppress(RuntimeError):
        async with Actor(configure_logging=False):
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

    # Updated expected number of log records (an extra record is now captured)
    assert len(caplog.records) == 14

    # Record 0: Extra Pytest context log
    assert caplog.records[0].levelno == logging.DEBUG
    assert caplog.records[0].message.startswith('Running in Pytest')

    # Record 1: Duplicate Pytest context log
    assert caplog.records[1].levelno == logging.DEBUG
    assert caplog.records[0].message.startswith('Running in Pytest')

    # Record 2: Initializing Actor...
    assert caplog.records[2].levelno == logging.INFO
    assert caplog.records[2].message == 'Initializing Actor...'

    # Record 3: System info
    assert caplog.records[3].levelno == logging.INFO
    assert caplog.records[3].message == 'System info'

    # Record 4: Event manager initialized
    assert caplog.records[4].levelno == logging.DEBUG
    assert caplog.records[4].message == 'Event manager initialized'

    # Record 5: Charging manager initialized
    assert caplog.records[5].levelno == logging.DEBUG
    assert caplog.records[5].message == 'Charging manager initialized'

    # Record 6: Debug message
    assert caplog.records[6].levelno == logging.DEBUG
    assert caplog.records[6].message == 'Debug message'

    # Record 7: Info message
    assert caplog.records[7].levelno == logging.INFO
    assert caplog.records[7].message == 'Info message'

    # Record 8: Warning message
    assert caplog.records[8].levelno == logging.WARNING
    assert caplog.records[8].message == 'Warning message'

    # Record 9: Error message
    assert caplog.records[9].levelno == logging.ERROR
    assert caplog.records[9].message == 'Error message'

    # Record 10: Exception message with traceback (ValueError)
    assert caplog.records[10].levelno == logging.ERROR
    assert caplog.records[10].message == 'Exception message'
    assert caplog.records[10].exc_info is not None
    assert caplog.records[10].exc_info[0] is ValueError
    assert isinstance(caplog.records[10].exc_info[1], ValueError)
    assert str(caplog.records[10].exc_info[1]) == 'Dummy ValueError'

    # Record 11: Multiline log message
    assert caplog.records[11].levelno == logging.INFO
    assert caplog.records[11].message == 'Multi\nline\nlog\nmessage'

    # Record 12: Actor failed with an exception (RuntimeError)
    assert caplog.records[12].levelno == logging.ERROR
    assert caplog.records[12].message == 'Actor failed with an exception'
    assert caplog.records[12].exc_info is not None
    assert caplog.records[12].exc_info[0] is RuntimeError
    assert isinstance(caplog.records[12].exc_info[1], RuntimeError)
    assert str(caplog.records[12].exc_info[1]) == 'Dummy RuntimeError'

    # Record 13: Exiting Actor
    assert caplog.records[13].levelno == logging.INFO
    assert caplog.records[13].message == 'Exiting Actor'
