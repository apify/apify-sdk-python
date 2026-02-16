from __future__ import annotations

from enum import Enum
from unittest.mock import patch

import pytest

from apify._utils import get_system_info, is_running_in_ipython, maybe_extract_enum_member_value


def test_ipython_detection_when_active() -> None:
    """Test that is_running_in_ipython returns True when __IPYTHON__ is set."""
    import builtins

    original = getattr(builtins, '__IPYTHON__', None)
    try:
        builtins.__IPYTHON__ = True  # type: ignore[attr-defined]
        assert is_running_in_ipython() is True
    finally:
        if original is None:
            if hasattr(builtins, '__IPYTHON__'):
                del builtins.__IPYTHON__
        else:
            builtins.__IPYTHON__ = original  # type: ignore[attr-defined]


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


def test_maybe_extract_enum_member_value_with_enum() -> None:
    """Test that enum members are unwrapped to their values."""

    class Color(Enum):
        RED = 'red'
        BLUE = 'blue'

    assert maybe_extract_enum_member_value(Color.RED) == 'red'
    assert maybe_extract_enum_member_value(Color.BLUE) == 'blue'


def test_maybe_extract_enum_member_value_with_non_enum() -> None:
    """Test that non-enum values are returned unchanged."""
    assert maybe_extract_enum_member_value('hello') == 'hello'
    assert maybe_extract_enum_member_value(42) == 42
    assert maybe_extract_enum_member_value(None) is None
