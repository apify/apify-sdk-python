"""Apify Actor integration for Scrapy projects.

This module transforms a Scrapy project into an Apify Actor, handling the configuration of logging, patching Scrapy's
logging system, and establishing the required environment to run the Scrapy spider within the Apify platform.

This file is specifically designed to be executed when the project is run as an Apify Actor using `apify run` locally
or being run on the Apify platform. It is not being executed when running the project as a Scrapy project using
`scrapy crawl title_spider`.

We recommend you do not modify this file unless you really know what you are doing.
"""
# ruff: noqa: E402, I001

from __future__ import annotations
import asyncio
from twisted.internet import asyncioreactor

# Install Twisted's asyncio reactor before importing any other Twisted or Scrapy components.
asyncioreactor.install(asyncio.get_event_loop())  # type: ignore[no-untyped-call]

import os
from apify.scrapy import initialize_logging, run_scrapy_actor
from .main import main

# Ensure the location to the Scrapy settings module is defined.
os.environ['SCRAPY_SETTINGS_MODULE'] = 'src.settings'


if __name__ == '__main__':
    initialize_logging()
    run_scrapy_actor(main())
