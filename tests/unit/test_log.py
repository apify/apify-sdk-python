from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apify.log import _configure_logging

if TYPE_CHECKING:
    import pytest


def test_configure_logging_debug_level(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that apify_client logger is set to DEBUG when global level is DEBUG."""
    monkeypatch.setenv('CRAWLEE_LOG_LEVEL', 'DEBUG')
    _configure_logging()
    apify_client_logger = logging.getLogger('apify_client')
    assert apify_client_logger.level == logging.DEBUG


def test_configure_logging_info_level(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that apify_client logger is set to INFO when global level > DEBUG."""
    monkeypatch.setenv('CRAWLEE_LOG_LEVEL', 'INFO')
    _configure_logging()
    apify_client_logger = logging.getLogger('apify_client')
    assert apify_client_logger.level == logging.INFO
