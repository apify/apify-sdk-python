from __future__ import annotations

import os

_running_in_scrapy = False
"""Whether `run_scrapy_actor` is currently driving the process."""


def mark_running_in_scrapy() -> None:
    """Record that the current process is being driven by the Apify-Scrapy integration.

    Called by `run_scrapy_actor` before the Actor's main coroutine runs, so `is_running_in_scrapy` already
    reports the correct value by the time the Actor initializes.
    """
    global _running_in_scrapy  # noqa: PLW0603
    _running_in_scrapy = True


def is_running_in_scrapy() -> bool:
    """Whether the Actor is running as part of a Scrapy project.

    Returns `True` when `run_scrapy_actor` is driving the process, or when the `SCRAPY_SETTINGS_MODULE`
    environment variable is set (by the Scrapy CLI or by the Actor's entry point). Detecting a real Scrapy
    run this way, rather than by whether `scrapy` merely happens to be importable, keeps the `exit_process`
    default correct for images where Scrapy is only a transitive dependency.
    """
    return _running_in_scrapy or bool(os.environ.get('SCRAPY_SETTINGS_MODULE'))
