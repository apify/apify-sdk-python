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

    expected_logs = [
        (logging.DEBUG, 'Debug message'),
        (logging.INFO, 'Info message'),
        (logging.WARNING, 'Warning message'),
        (logging.ERROR, 'Error message'),
        (logging.ERROR, 'Exception message', ValueError('Dummy ValueError')),
        (logging.INFO, 'Multi\nline\nlog\nmessage'),
        (logging.ERROR, 'Actor failed with an exception', RuntimeError('Dummy RuntimeError')),
        (logging.INFO, 'Exiting Actor'),
    ]

    for level, message, *exception in expected_logs:
        matching = [r for r in records if r.message == message]
        assert len(matching) == 1, f'Expected exactly one log record with message {message!r}, found {len(matching)}'
        record = matching[0]
        assert record.levelno == level
        if exception:
            assert record.exc_info is not None
            assert record.exc_info[0] is type(exception[0])
            assert isinstance(record.exc_info[1], type(exception[0]))
            assert str(record.exc_info[1]) == str(exception[0])
