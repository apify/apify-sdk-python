from __future__ import annotations

from scrapy.utils.reactor import install_reactor

install_reactor('twisted.internet.asyncioreactor.AsyncioSelectorReactor')

import os  # noqa: E402, I001

from apify.scrapy import initialize_logging, run_scrapy_actor  # noqa: E402

from .main import main  # noqa: E402

os.environ['SCRAPY_SETTINGS_MODULE'] = 'src.settings'

if __name__ == '__main__':
    initialize_logging()
    run_scrapy_actor(main())
