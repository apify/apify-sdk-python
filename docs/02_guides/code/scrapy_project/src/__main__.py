# ruff: noqa: E402, I001

from __future__ import annotations
from twisted.internet import asyncioreactor

# Install Twisted's asyncio reactor before importing any other Twisted or Scrapy components.
asyncioreactor.install()  # type: ignore[no-untyped-call]

import os
from apify.scrapy import initialize_logging, run_scrapy_actor
from .main import main

# Ensure the location to the Scrapy settings module is defined.
os.environ['SCRAPY_SETTINGS_MODULE'] = 'src.settings'


if __name__ == '__main__':
    initialize_logging()
    run_scrapy_actor(main())
