"""Apify Actor integration for Scrapy projects.

This module transforms a Scrapy project into an Apify Actor, handling the configuration of logging, patching Scrapy's
logging system, and establishing the required environment to run the Scrapy spider within the Apify platform.

This file is specifically designed to be executed when the project is run as an Apify Actor using `apify run` locally
or being run on the Apify platform. It is not being executed when running the project as a Scrapy project using
`scrapy crawl title_spider`.

We recommend you do not modify this file unless you really know what you are doing.
"""

# ruff: noqa: E402

# We need to configure the logging first before we import anything else, so that nothing else imports
# `scrapy.utils.log` before we patch it.
from __future__ import annotations

from logging import StreamHandler, getLogger
from typing import Any

from scrapy.utils import log as scrapy_logging
from scrapy.utils.project import get_project_settings

from apify.log import ActorLogFormatter

# Define names of the loggers.
MAIN_LOGGER_NAMES = ['apify', 'apify_client', 'scrapy']
OTHER_LOGGER_NAMES = ['filelock', 'hpack', 'httpcore', 'httpx', 'protego', 'twisted']
ALL_LOGGER_NAMES = MAIN_LOGGER_NAMES + OTHER_LOGGER_NAMES

# To change the logging level, modify the `LOG_LEVEL` field in `settings.py`. If the field is not present in the file,
# Scrapy will default to `DEBUG`. This setting applies to all loggers. If you wish to change the logging level for
# a specific logger, do it in this file.
settings = get_project_settings()
LOGGING_LEVEL = settings['LOG_LEVEL']

# Define a logging handler which will be used for the loggers.
apify_handler = StreamHandler()
apify_handler.setFormatter(ActorLogFormatter(include_logger_name=True))


def configure_logger(logger_name: str | None, log_level: str, *handlers: StreamHandler) -> None:
    """Configure a logger with the specified settings.

    Args:
        logger_name: The name of the logger to be configured.
        log_level: The desired logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR', ...).
        handlers: Optional list of logging handlers.
    """
    logger = getLogger(logger_name)
    logger.setLevel(log_level)
    logger.handlers = []

    for handler in handlers:
        logger.addHandler(handler)


# Apify loggers have to be set up here and in the `new_configure_logging` as well to be able to use them both from
# the `main.py` and Scrapy components.
for logger_name in MAIN_LOGGER_NAMES:
    configure_logger(logger_name, LOGGING_LEVEL, apify_handler)

# We can't attach our log handler to the loggers normally, because Scrapy would remove them in the `configure_logging`
# call here: https://github.com/scrapy/scrapy/blob/2.11.0/scrapy/utils/log.py#L113 (even though
# `disable_existing_loggers` is set to False :facepalm:). We need to monkeypatch Scrapy's `configure_logging` method
# like this, so that our handler is attached right after Scrapy calls the `configure_logging` method, because
# otherwise we would lose some log messages.
old_configure_logging = scrapy_logging.configure_logging


def new_configure_logging(*args: Any, **kwargs: Any) -> None:
    """Configure logging for Scrapy and root loggers to ensure consistent logging behavior.

    We need to manually configure both the root logger and all Scrapy-associated loggers. Configuring only the root
    logger is not sufficient, as Scrapy will override it with its own settings. Scrapy uses these four primary
    loggers - https://github.com/scrapy/scrapy/blob/2.11.0/scrapy/utils/log.py#L60:L77. Therefore, we configure here
    these four loggers and the root logger.
    """
    old_configure_logging(*args, **kwargs)

    # We modify the root (None) logger to ensure proper display of logs from spiders when using the `self.logger`
    # property within spiders. See details in the Spider logger property:
    # https://github.com/scrapy/scrapy/blob/2.11.0/scrapy/spiders/__init__.py#L43:L46.
    configure_logger(None, LOGGING_LEVEL, apify_handler)

    # We modify other loggers only by setting up their log level. A custom log handler is added
    # only to the root logger to avoid duplicate log messages.
    for logger_name in ALL_LOGGER_NAMES:
        configure_logger(logger_name, LOGGING_LEVEL)

    # Set the HTTPX logger explicitly to the WARNING level, because it is too verbose and spams the logs with useless
    # messages, especially when running on the platform.
    configure_logger('httpx', 'WARNING')


scrapy_logging.configure_logging = new_configure_logging

# Now we can do the rest of the setup.
import asyncio
import os

import nest_asyncio
from scrapy.utils.reactor import install_reactor

from .main import main

# For compatibility between Twisted (used by Scrapy) and AsyncIO (used by Apify) asynchronous libraries, it is
# necessary to set the Twisted reactor to `AsyncioSelectorReactor`. This setup allows the two asynchronous libraries
# to work together.
#
# Note: The reactor must be installed before applying `nest_asyncio.apply()`, otherwise, it will not work correctly
# on Windows.
install_reactor('twisted.internet.asyncioreactor.AsyncioSelectorReactor')
nest_asyncio.apply()

# Specify the path to the Scrapy project settings module.
os.environ['SCRAPY_SETTINGS_MODULE'] = 'src.settings'

# Run the Apify main coroutine in the event loop.
asyncio.run(main())
