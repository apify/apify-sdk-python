from __future__ import annotations

from enum import Enum
from unittest.mock import patch

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


def test_get_system_info_includes_ipython_flag() -> None:
    """Test that get_system_info includes is_running_in_ipython when in IPython."""
    with patch('apify._utils.is_running_in_ipython', return_value=True):
        info = get_system_info()
        assert info['is_running_in_ipython'] is True


def test_get_system_info_excludes_ipython_flag() -> None:
    """Test that get_system_info excludes is_running_in_ipython when not in IPython."""
    with patch('apify._utils.is_running_in_ipython', return_value=False):
        info = get_system_info()
        assert 'is_running_in_ipython' not in info


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
