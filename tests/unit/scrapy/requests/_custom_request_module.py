from __future__ import annotations

from scrapy import Request


class CustomRequest(Request):
    """A custom Scrapy `Request` subclass used to exercise reconstruction across a process boundary.

    It deliberately lives in its own module (not imported by the test at collection time) so a test can
    drop it from `sys.modules` and verify reconstruction imports it on demand, mimicking an Actor that
    migrates to a fresh process before its spider has imported this class.
    """
