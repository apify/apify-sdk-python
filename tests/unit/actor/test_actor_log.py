from __future__ import annotations

import contextlib
import logging
import sys
from typing import TYPE_CHECKING

from apify_client import __version__ as apify_client_version

from apify import Actor, __version__
from apify._log import logger

if TYPE_CHECKING:
    import pytest


class TestActorLog:
    async def test_actor_log(
        self: TestActorLog,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        caplog.set_level(logging.DEBUG, logger='apify')
        monkeypatch.setenv('APIFY_IS_AT_HOME', '1')

        with contextlib.suppress(RuntimeError):
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

        assert len(caplog.records) == 12

        assert caplog.records[0].levelno == logging.INFO
        assert caplog.records[0].message == 'Initializing Actor...'

        assert caplog.records[1].levelno == logging.INFO
        assert caplog.records[1].message == 'System info'
        assert getattr(caplog.records[1], 'apify_sdk_version', None) == __version__
        assert getattr(caplog.records[1], 'apify_client_version', None) == apify_client_version
        assert getattr(caplog.records[1], 'python_version', None) == '.'.join([str(x) for x in sys.version_info[:3]])
        assert getattr(caplog.records[1], 'os', None) == sys.platform

        assert caplog.records[2].levelno == logging.DEBUG
        assert caplog.records[2].message.startswith('APIFY_ACTOR_EVENTS_WS_URL env var not set')

        assert caplog.records[3].levelno == logging.DEBUG
        assert caplog.records[3].message == 'Debug message'

        assert caplog.records[4].levelno == logging.INFO
        assert caplog.records[4].message == 'Info message'

        assert caplog.records[5].levelno == logging.WARNING
        assert caplog.records[5].message == 'Warning message'

        assert caplog.records[6].levelno == logging.ERROR
        assert caplog.records[6].message == 'Error message'

        assert caplog.records[7].levelno == logging.ERROR
        assert caplog.records[7].message == 'Exception message'
        assert caplog.records[7].exc_info is not None
        assert caplog.records[7].exc_info[0] is ValueError
        assert isinstance(caplog.records[7].exc_info[1], ValueError)
        assert str(caplog.records[7].exc_info[1]) == 'Dummy ValueError'

        assert caplog.records[8].levelno == logging.INFO
        assert caplog.records[8].message == 'Multi\nline\nlog\nmessage'

        assert caplog.records[9].levelno == logging.ERROR
        assert caplog.records[9].message == 'Actor failed with an exception'
        assert caplog.records[9].exc_info is not None
        assert caplog.records[9].exc_info[0] is RuntimeError
        assert isinstance(caplog.records[9].exc_info[1], RuntimeError)
        assert str(caplog.records[9].exc_info[1]) == 'Dummy RuntimeError'

        assert caplog.records[10].levelno == logging.INFO
        assert caplog.records[10].message == 'Exiting Actor'

        assert caplog.records[11].levelno == logging.DEBUG
        assert caplog.records[11].message == 'Not calling sys.exit(91) because Actor is running in an unit test'
