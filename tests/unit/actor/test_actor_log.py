from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

from apify import Actor
from apify.log import logger

if TYPE_CHECKING:
    import pytest


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

    # Updated expected number of log records (additional debug messages added)
    assert len(caplog.records) == 16

    # Record 0: First Pytest context log
    assert caplog.records[0].levelno == logging.DEBUG
    assert caplog.records[0].message.startswith('Running in Pytest')

    # Record 1: Duplicate Pytest context log
    assert caplog.records[1].levelno == logging.DEBUG
    assert caplog.records[1].message.startswith('Running in Pytest')

    # Record 2: Logging configured
    assert caplog.records[2].levelno == logging.DEBUG
    assert caplog.records[2].message == 'Logging configured'

    # Record 3: Initializing Actor
    assert caplog.records[3].levelno == logging.INFO
    assert caplog.records[3].message == 'Initializing Actor'

    # Record 4: Configuration initialized
    assert caplog.records[4].levelno == logging.DEBUG
    assert caplog.records[4].message == 'Configuration initialized'

    # Record 5: Storage client initialized
    assert caplog.records[5].levelno == logging.DEBUG
    assert caplog.records[5].message == 'Storage client initialized'

    # Record 6: Event manager initialized
    assert caplog.records[6].levelno == logging.DEBUG
    assert caplog.records[6].message == 'Event manager initialized'

    # Record 7: Charging manager initialized
    assert caplog.records[7].levelno == logging.DEBUG
    assert caplog.records[7].message == 'Charging manager initialized'

    # Record 8: Debug message
    assert caplog.records[8].levelno == logging.DEBUG
    assert caplog.records[8].message == 'Debug message'

    # Record 9: Info message
    assert caplog.records[9].levelno == logging.INFO
    assert caplog.records[9].message == 'Info message'

    # Record 10: Warning message
    assert caplog.records[10].levelno == logging.WARNING
    assert caplog.records[10].message == 'Warning message'

    # Record 11: Error message
    assert caplog.records[11].levelno == logging.ERROR
    assert caplog.records[11].message == 'Error message'

    # Record 12: Exception message with traceback (ValueError)
    assert caplog.records[12].levelno == logging.ERROR
    assert caplog.records[12].message == 'Exception message'
    assert caplog.records[12].exc_info is not None
    assert caplog.records[12].exc_info[0] is ValueError
    assert isinstance(caplog.records[12].exc_info[1], ValueError)
    assert str(caplog.records[12].exc_info[1]) == 'Dummy ValueError'

    # Record 13: Multiline log message
    assert caplog.records[13].levelno == logging.INFO
    assert caplog.records[13].message == 'Multi\nline\nlog\nmessage'

    # Record 14: Actor failed with an exception (RuntimeError)
    assert caplog.records[14].levelno == logging.ERROR
    assert caplog.records[14].message == 'Actor failed with an exception'
    assert caplog.records[14].exc_info is not None
    assert caplog.records[14].exc_info[0] is RuntimeError
    assert isinstance(caplog.records[14].exc_info[1], RuntimeError)
    assert str(caplog.records[14].exc_info[1]) == 'Dummy RuntimeError'

    # Record 15: Exiting Actor
    assert caplog.records[15].levelno == logging.INFO
    assert caplog.records[15].message == 'Exiting Actor'
