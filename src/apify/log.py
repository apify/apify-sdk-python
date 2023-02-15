import json
import logging
import textwrap
import traceback
from typing import Any, Dict

from colorama import Fore, Style, just_fix_windows_console

just_fix_windows_console()


# Name of the logger used throughout the library
logger_name = __name__.split('.')[0]

# Logger used throughout the library
logger = logging.getLogger(logger_name)


_LOG_LEVEL_COLOR = {
    logging.DEBUG: Fore.BLUE,
    logging.INFO: Fore.GREEN,
    logging.WARNING: Fore.YELLOW,
    logging.ERROR: Fore.RED,
    logging.CRITICAL: Fore.RED,
}

_LOG_LEVEL_SHORT_ALIAS = {
    logging.DEBUG: 'DEBUG',
    logging.INFO: 'INFO ',
    logging.WARNING: 'WARN ',
    logging.ERROR: 'ERROR',
}


class ActorLogFormatter(logging.Formatter):
    """Log formatter that prints out the log message nicely formatted, with colored level and stringified extra fields."""

    empty_record = logging.LogRecord('dummy', 0, 'dummy', 0, 'dummy', None, None)

    def _get_extra_fields(self, record: logging.LogRecord) -> Dict[str, Any]:
        extra_fields: Dict[str, Any] = {}
        for key, value in record.__dict__.items():
            if key not in self.empty_record.__dict__:
                extra_fields[key] = value

        return extra_fields

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record nicely.

        This formats the log record so that it:
        - starts with the level (colorized, and padded to 5 chars so that it is nicely aligned)
        - then has the actual log message
        - then has the stringified extra log fields
        - then, if an exception is a part of the log record, prints the formatted exception
        """
        level_string = ''
        if record.levelno != logging.NOTSET:
            color_code = _LOG_LEVEL_COLOR.get(record.levelno, '')
            short_alias = _LOG_LEVEL_SHORT_ALIAS.get(record.levelno, record.levelname)
            level_string = f'{color_code}{short_alias}{Style.RESET_ALL} '

        exception_string = ''
        if record.exc_info:
            exc_info = record.exc_info
            record.exc_info = None
            exception_string = ''.join(traceback.format_exception(*exc_info)).rstrip()
            exception_string = '\n' + textwrap.indent(exception_string, '      ')

        extra = self._get_extra_fields(record)
        extra_string = ''
        if extra:
            extra_string = f' {Fore.LIGHTBLACK_EX}({json.dumps(extra, ensure_ascii=False, default=str)}){Style.RESET_ALL}'

        log_string = super().format(record)
        log_string = textwrap.indent(log_string, '      ').lstrip()

        return f'{level_string}{log_string}{extra_string}{exception_string}'
