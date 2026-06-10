from __future__ import annotations

from scrapy import Request


class CustomRequest(Request):
    """A custom Scrapy `Request` subclass living in its own module, so a test can drop it from `sys.modules`
    and verify reconstruction imports it on demand (mimicking an Actor migrating to a fresh process).
    """
