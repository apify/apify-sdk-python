from __future__ import annotations

import logging

from apify_shared.utils import ignore_docs
from crawlee._log_config import CrawleeLogFormatter, configure_logger, get_configured_log_level

# Name of the logger used throughout the library (resolves to 'apify')
logger_name = __name__.split('.')[0]

# Logger used throughout the library
logger = logging.getLogger(logger_name)


@ignore_docs
class ActorLogFormatter(CrawleeLogFormatter):  # noqa: D101 (Inherited from parent class)
    pass


def _configure_logging() -> None:
    apify_client_logger = logging.getLogger('apify_client')
    configure_logger(apify_client_logger, remove_old_handlers=True)

    level = get_configured_log_level()

    # Keep apify_client logger quiet unless debug logging is requested
    if level > logging.DEBUG:
        apify_client_logger.setLevel(logging.INFO)
    else:
        apify_client_logger.setLevel(level)

    # Silence HTTPX logger unless debug logging is requested
    httpx_logger = logging.getLogger('httpx')
    if level > logging.DEBUG:
        httpx_logger.setLevel(logging.WARNING)
    else:
        httpx_logger.setLevel(level)

    # Use configured log level for apify logger
    apify_logger = logging.getLogger('apify')
    configure_logger(apify_logger, remove_old_handlers=True)


def create_redirect_logger(name: str,
                           *,
                           default_level: int =logging.INFO,
                           respect_original_log_level: bool = True,
                           ) -> logging.Logger:
    """Create a logger for redirecting logs from another Actor.

    Args:
        name: The name of the logger.
        default_level: All logs will be emitted on this level, regardless of the original level.
        respect_original_log_level: Try to use the original log level of the other actor logger and use `default_level`
         only if the original level is not determined.

    Returns:
        The created logger.
    """
    to_logger=logging.getLogger(name)
    if respect_original_log_level:
        to_logger.addFilter(
            _RedirectLogLevelFilter(
                default_level=default_level,
            )
        )
    else:
        to_logger.addFilter(_FixedLevelFilter(default_level))

    return to_logger

class _FixedLevelFilter(logging.Filter):

    def __init__(self, name: str="", default_level: int =logging.INFO):
        super().__init__(name)
        self._default_level = default_level

    def filter(self, record):
        """Try to extract log level from the message content and set it accordingly."""
        record.levelno = self.default_level
        record.levelname = logging.getLevelName(record.levelno)
        return True


class _RedirectLogLevelFilter(logging.Filter):

    def __init__(self, name: str="", default_level: int =logging.INFO):
        super().__init__(name)
        self._default_level = default_level

    def _guess_log_level_from_message(self, message: str) -> int:
        """Guess the log level from the message."""

        # Using only levels explicitly mentioned in logging module
        known_levels = ("CRITICAL", "FATAL", "ERROR", "WARN", "WARNING", "INFO", "DEBUG", "NOTSET")
        for level in known_levels:
            if level in message:
                return logging.getLevelName(level)
        # Unknown log level. Fall back to the default.
        return self._default_level

    def filter(self, record):
        """Try to extract log level from the message content and set it accordingly."""
        record.levelno = self._guess_log_level_from_message(record.msg)
        record.levelname = logging.getLevelName(record.levelno)
        return True
