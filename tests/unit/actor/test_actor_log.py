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
        async with Actor(configure_logging=False, exit_process=False):
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

    records = caplog.records

    # Expected number of log records
    assert len(records) == 13

    # Record 0: Initializing Actor
    assert records[0].levelno == logging.INFO
    assert records[0].message == 'Initializing Actor'

    # Record 1: Configuration initialized
    assert records[1].levelno == logging.DEBUG
    assert records[1].message == 'Configuration initialized'

    # Record 2: Storage client initialized
    assert records[2].levelno == logging.DEBUG
    assert records[2].message == 'Storage client initialized'

    # Record 3: Event manager initialized
    assert records[3].levelno == logging.DEBUG
    assert records[3].message == 'Event manager initialized'

    # Record 4: Charging manager initialized
    assert records[4].levelno == logging.DEBUG
    assert records[4].message == 'Charging manager initialized'

    # Record 5: Debug message
    assert records[5].levelno == logging.DEBUG
    assert records[5].message == 'Debug message'

    # Record 6: Info message
    assert records[6].levelno == logging.INFO
    assert records[6].message == 'Info message'

    # Record 7: Warning message
    assert records[7].levelno == logging.WARNING
    assert records[7].message == 'Warning message'

    # Record 8: Error message
    assert records[8].levelno == logging.ERROR
    assert records[8].message == 'Error message'

    # Record 9: Exception message with traceback (ValueError)
    assert records[9].levelno == logging.ERROR
    assert records[9].message == 'Exception message'
    assert records[9].exc_info is not None
    assert records[9].exc_info[0] is ValueError
    assert isinstance(records[9].exc_info[1], ValueError)
    assert str(records[9].exc_info[1]) == 'Dummy ValueError'

    # Record 10: Multiline log message
    assert records[10].levelno == logging.INFO
    assert records[10].message == 'Multi\nline\nlog\nmessage'

    # Record 11: Actor failed with an exception (RuntimeError)
    assert records[11].levelno == logging.ERROR
    assert records[11].message == 'Actor failed with an exception'
    assert records[11].exc_info is not None
    assert records[11].exc_info[0] is RuntimeError
    assert isinstance(records[11].exc_info[1], RuntimeError)
    assert str(records[11].exc_info[1]) == 'Dummy RuntimeError'

    # Record 12: Exiting Actor
    assert records[12].levelno == logging.INFO
    assert records[12].message == 'Exiting Actor'
