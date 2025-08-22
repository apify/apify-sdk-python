from __future__ import annotations

import logging
from typing import Any

from scrapy.utils import log as scrapy_logging
from scrapy.utils.project import get_project_settings

from apify.log import ActorLogFormatter

# Define logger names.
_PRIMARY_LOGGERS = ['apify', 'apify_client', 'scrapy']
_SUPPLEMENTAL_LOGGERS = ['filelock', 'hpack', 'httpcore', 'protego', 'twisted']
_ALL_LOGGERS = _PRIMARY_LOGGERS + _SUPPLEMENTAL_LOGGERS


def _configure_logger(name: str | None, logging_level: str, handler: logging.Handler) -> None:
    """Clear and reconfigure the logger."""
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.setLevel(logging_level)
    logger.addHandler(handler)
    logger.propagate = False


def initialize_logging() -> None:
    """Configure logging for Apify Actors and adjust Scrapy's logging settings."""
    # Retrieve Scrapy project settings and determine the logging level.
    settings = get_project_settings()
    logging_level = settings.get('LOG_LEVEL', 'INFO')  # Default to INFO.

    # Create a custom handler with the Apify log formatter.
    handler = logging.StreamHandler()
    handler.setFormatter(ActorLogFormatter(include_logger_name=True))

    # Configure the root logger and all other defined loggers.
    for logger_name in [None, *_ALL_LOGGERS]:
        _configure_logger(logger_name, logging_level, handler)

    # Monkey-patch Scrapy's logging configuration to re-apply our settings.
    original_configure_logging = scrapy_logging.configure_logging

    def new_configure_logging(*args: Any, **kwargs: Any) -> None:
        original_configure_logging(*args, **kwargs)
        for logger_name in [None, *_ALL_LOGGERS]:
            _configure_logger(logger_name, logging_level, handler)

    scrapy_logging.configure_logging = new_configure_logging
