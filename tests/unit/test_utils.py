from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from apify._utils import (
    docs_group,
    docs_name,
    get_default_http_compression,
    get_system_info,
    is_running_in_ipython,
)


def test_ipython_detection_when_active() -> None:
    """Test that is_running_in_ipython returns True when __IPYTHON__ is set."""
    import builtins

    original = getattr(builtins, '__IPYTHON__', None)
    try:
        builtins.__IPYTHON__ = True  # ty: ignore[unresolved-attribute]
        assert is_running_in_ipython() is True
    finally:
        if original is None:
            if hasattr(builtins, '__IPYTHON__'):
                del builtins.__IPYTHON__
        else:
            builtins.__IPYTHON__ = original  # ty: ignore[unresolved-attribute]


@pytest.mark.parametrize(
    'ipython_running',
    [
        pytest.param(True, id='in_ipython'),
        pytest.param(False, id='not_in_ipython'),
    ],
)
def test_get_system_info_ipython_flag(*, ipython_running: bool) -> None:
    """Test that get_system_info correctly reflects the is_running_in_ipython flag."""
    with patch('apify._utils.is_running_in_ipython', return_value=ipython_running):
        info = get_system_info()
        assert info['is_running_in_ipython'] is ipython_running


if TYPE_CHECKING:
    # Regression guard: if `docs_group`/`docs_name` stop being identity-typed (`Callable[[T], T]`),
    # the decorated classes degrade to `Unknown`, the accesses below stop erroring, and the
    # then-unused suppressions fail the type check (`unused-ignore-comment = "error"`).

    @docs_group('Actor')
    class _DocsGroupDecorated:
        pass

    @docs_name('Renamed')
    class _DocsNameDecorated:
        pass

    _ = _DocsGroupDecorated.nonexistent  # ty: ignore[unresolved-attribute]
    _ = _DocsNameDecorated.nonexistent  # ty: ignore[unresolved-attribute]


def test_get_default_http_compression_prefers_brotli() -> None:
    """Brotli is the default since the SDK installs the `apify-client[brotli]` extra (present in the dev env)."""
    assert get_default_http_compression() == 'brotli'


def test_get_default_http_compression_falls_back_to_gzip(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the optional `brotli` package isn't importable, the default falls back to gzip."""
    monkeypatch.setattr('apify._utils.find_spec', lambda _name: None)
    assert get_default_http_compression() == 'gzip'


def test_docs_decorators_return_original_object() -> None:
    """Test that `docs_group` and `docs_name` return the decorated object unchanged."""

    class Sample:
        pass

    assert docs_group('Actor')(Sample) is Sample
    assert docs_name('Renamed')(Sample) is Sample
