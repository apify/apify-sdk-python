from __future__ import annotations

import logging
import os

from apify.log import _configure_logging


def test_configure_logging_debug_level() -> None:
    """Test that apify_client logger is set to DEBUG when global level is DEBUG."""
    original = os.environ.get('CRAWLEE_LOG_LEVEL')
    try:
        os.environ['CRAWLEE_LOG_LEVEL'] = 'DEBUG'
        _configure_logging()
        apify_client_logger = logging.getLogger('apify_client')
        assert apify_client_logger.level == logging.DEBUG
    finally:
        if original is None:
            os.environ.pop('CRAWLEE_LOG_LEVEL', None)
        else:
            os.environ['CRAWLEE_LOG_LEVEL'] = original


def test_configure_logging_info_level() -> None:
    """Test that apify_client logger is set to INFO when global level > DEBUG."""
    original = os.environ.get('CRAWLEE_LOG_LEVEL')
    try:
        os.environ['CRAWLEE_LOG_LEVEL'] = 'INFO'
        _configure_logging()
        apify_client_logger = logging.getLogger('apify_client')
        assert apify_client_logger.level == logging.INFO
    finally:
        if original is None:
            os.environ.pop('CRAWLEE_LOG_LEVEL', None)
        else:
            os.environ['CRAWLEE_LOG_LEVEL'] = original
