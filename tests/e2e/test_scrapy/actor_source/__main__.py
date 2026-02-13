from __future__ import annotations

from scrapy.utils.reactor import install_reactor

install_reactor('twisted.internet.asyncioreactor.AsyncioSelectorReactor')

import os

from apify.scrapy import initialize_logging, run_scrapy_actor

from .main import main

os.environ['SCRAPY_SETTINGS_MODULE'] = 'src.settings'

if __name__ == '__main__':
    initialize_logging()
    run_scrapy_actor(main())
