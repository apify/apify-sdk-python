from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apify.scrapy._warnings import logger_once, warn_about_uninitialized_actor

if TYPE_CHECKING:
    import pytest


def test_the_uninitialized_actor_warning_is_logged_once(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The scheduler and the extension both report the missing Actor, but the process logs the warning only once."""
    monkeypatch.setattr(logger_once, '_seen', set())

    with caplog.at_level(logging.WARNING, logger='apify.scrapy._warnings'):
        warn_about_uninitialized_actor()
        warn_about_uninitialized_actor()

    warnings = [record for record in caplog.records if 'Actor is not initialized' in record.getMessage()]
    assert len(warnings) == 1
    assert warnings[0].levelno == logging.WARNING
