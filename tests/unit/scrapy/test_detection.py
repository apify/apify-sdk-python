from __future__ import annotations

from typing import TYPE_CHECKING

from apify.scrapy import _detection

if TYPE_CHECKING:
    import pytest


def test_not_in_scrapy_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the runner flag or `SCRAPY_SETTINGS_MODULE`, the process is not treated as Scrapy."""
    monkeypatch.setattr(_detection, '_running_in_scrapy', False)
    monkeypatch.delenv('SCRAPY_SETTINGS_MODULE', raising=False)
    assert _detection.is_running_in_scrapy() is False


def test_detected_via_settings_module_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """`SCRAPY_SETTINGS_MODULE` (set by the Scrapy CLI or entry point) marks a Scrapy run."""
    monkeypatch.setattr(_detection, '_running_in_scrapy', False)
    monkeypatch.setenv('SCRAPY_SETTINGS_MODULE', 'src.settings')
    assert _detection.is_running_in_scrapy() is True


def test_detected_via_runner_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """`mark_running_in_scrapy` (called by `run_scrapy_actor`) marks a Scrapy run without any env var."""
    monkeypatch.setattr(_detection, '_running_in_scrapy', False)
    monkeypatch.delenv('SCRAPY_SETTINGS_MODULE', raising=False)
    _detection.mark_running_in_scrapy()
    assert _detection.is_running_in_scrapy() is True
