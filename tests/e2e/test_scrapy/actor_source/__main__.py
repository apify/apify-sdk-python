from __future__ import annotations

import os

from .main import main
from apify.scrapy import initialize_logging, run_scrapy_actor

os.environ['SCRAPY_SETTINGS_MODULE'] = 'src.settings'

if __name__ == '__main__':
    initialize_logging()
    run_scrapy_actor(main())
