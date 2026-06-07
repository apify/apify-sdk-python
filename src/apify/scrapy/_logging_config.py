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

# Mutable module state shared with the Scrapy logging monkey-patch installed by `initialize_logging`.
# `initialize_logging` refreshes `level`/`handler` on each call, and the patch (installed at most
# once) reads them so it always re-applies the latest configuration instead of values captured the
# first time it ran. Stored in a dict so the patch can read them without rebinding module globals.
_state: dict[str, Any] = {'level': 'INFO', 'handler': None, 'patched': False}


def _configure_logger(name: str | None, logging_level: str, handler: logging.Handler) -> None:
    """Clear and reconfigure the logger."""
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.setLevel(logging_level)
    logger.addHandler(handler)
    logger.propagate = False


def _configure_all_loggers() -> None:
    """Apply the Apify handler and level to the root logger and all defined loggers."""
    handler = _state['handler']
    if handler is None:
        return
    for logger_name in [None, *_ALL_LOGGERS]:
        _configure_logger(logger_name, _state['level'], handler)


def initialize_logging() -> None:
    """Configure logging for Apify Actors and adjust Scrapy's logging settings."""
    # Retrieve Scrapy project settings and determine the logging level.
    settings = get_project_settings()
    _state['level'] = settings.get('LOG_LEVEL', 'INFO')  # Default to INFO.

    # Create a custom handler with the Apify log formatter.
    handler = logging.StreamHandler()
    handler.setFormatter(ActorLogFormatter(include_logger_name=True))
    _state['handler'] = handler

    # Configure the root logger and all other defined loggers.
    _configure_all_loggers()

    # Monkey-patch Scrapy's logging configuration to re-apply our settings whenever Scrapy
    # reconfigures logging. Install the wrapper at most once; wrapping again on every call would
    # nest wrappers on top of each other.
    if _state['patched']:
        return

    original_configure_logging = scrapy_logging.configure_logging

    def new_configure_logging(*args: Any, **kwargs: Any) -> None:
        original_configure_logging(*args, **kwargs)
        _configure_all_loggers()

    scrapy_logging.configure_logging = new_configure_logging  # ty: ignore[invalid-assignment]
    _state['patched'] = True
