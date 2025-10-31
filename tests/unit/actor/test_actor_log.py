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

    # We skip the first entry, as it is related to the initialization of `lazy_object_proxy.Proxy` for `Actor`.
    records = caplog.records[1:]

    # Updated expected number of log records (additional debug messages added)
    assert len(records) == 14

    # Record 0: Logging configured
    assert records[0].levelno == logging.DEBUG
    assert records[0].message == 'Logging configured'

    # Record 1: Initializing Actor
    assert records[1].levelno == logging.INFO
    assert records[1].message == 'Initializing Actor'

    # Record 2: Configuration initialized
    assert records[2].levelno == logging.DEBUG
    assert records[2].message == 'Configuration initialized'

    # Record 3: Storage client initialized
    assert records[3].levelno == logging.DEBUG
    assert records[3].message == 'Storage client initialized'

    # Record 4: Event manager initialized
    assert records[4].levelno == logging.DEBUG
    assert records[4].message == 'Event manager initialized'

    # Record 5: Charging manager initialized
    assert records[5].levelno == logging.DEBUG
    assert records[5].message == 'Charging manager initialized'

    # Record 6: Debug message
    assert records[6].levelno == logging.DEBUG
    assert records[6].message == 'Debug message'

    # Record 7: Info message
    assert records[7].levelno == logging.INFO
    assert records[7].message == 'Info message'

    # Record 8: Warning message
    assert records[8].levelno == logging.WARNING
    assert records[8].message == 'Warning message'

    # Record 9: Error message
    assert records[9].levelno == logging.ERROR
    assert records[9].message == 'Error message'

    # Record 10: Exception message with traceback (ValueError)
    assert records[10].levelno == logging.ERROR
    assert records[10].message == 'Exception message'
    assert records[10].exc_info is not None
    assert records[10].exc_info[0] is ValueError
    assert isinstance(records[10].exc_info[1], ValueError)
    assert str(records[10].exc_info[1]) == 'Dummy ValueError'

    # Record 11: Multiline log message
    assert records[11].levelno == logging.INFO
    assert records[11].message == 'Multi\nline\nlog\nmessage'

    # Record 12: Actor failed with an exception (RuntimeError)
    assert records[12].levelno == logging.ERROR
    assert records[12].message == 'Actor failed with an exception'
    assert records[12].exc_info is not None
    assert records[12].exc_info[0] is RuntimeError
    assert isinstance(records[12].exc_info[1], RuntimeError)
    assert str(records[12].exc_info[1]) == 'Dummy RuntimeError'

    # Record 13: Exiting Actor
    assert records[13].levelno == logging.INFO
    assert records[13].message == 'Exiting Actor'
