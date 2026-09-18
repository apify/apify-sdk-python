from __future__ import annotations

import sys
from types import ModuleType
from typing import TYPE_CHECKING, Any

import pytest

from apify._try_import import FailedImport, install_import_hook, try_import

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def module() -> Iterator[Any]:
    """Register a throwaway module that the import guards can write their placeholders into."""
    mod = ModuleType('apify_test_try_import_target')
    sys.modules[mod.__name__] = mod
    install_import_hook(mod.__name__)
    yield mod
    del sys.modules[mod.__name__]


def test_successful_import_is_left_alone(module: Any) -> None:
    with try_import(module.__name__, 'symbol', extra_name='scrapy'):
        module.symbol = 'value'

    assert module.symbol == 'value'


def test_missing_module_names_the_apify_extra(module: Any) -> None:
    with try_import(module.__name__, 'symbol', extra_name='scrapy'):
        raise ModuleNotFoundError("No module named 'scrapy'")

    with pytest.raises(ImportError) as exc_info:
        _ = module.symbol

    assert str(exc_info.value) == (
        "No module named 'scrapy'. Install the optional 'scrapy' extra to use it: pip install 'apify[scrapy]'"
    )


def test_missing_module_names_one_of_several_extras(module: Any) -> None:
    with try_import(module.__name__, 'symbol', extra_name=['scrapy', 'other']):
        raise ModuleNotFoundError("No module named 'scrapy'")

    with pytest.raises(ImportError) as exc_info:
        _ = module.symbol

    assert str(exc_info.value) == (
        "No module named 'scrapy'. Install one of the optional extras 'scrapy', 'other' to use it, "
        "e.g. pip install 'apify[scrapy]'"
    )


def test_other_import_errors_keep_their_message(module: Any) -> None:
    with try_import(module.__name__, 'symbol', extra_name='scrapy'):
        raise ImportError('cannot import name X')

    with pytest.raises(ImportError, match=r'^cannot import name X$'):
        _ = module.symbol


def test_all_guarded_symbols_are_replaced(module: Any) -> None:
    with try_import(module.__name__, 'first', 'second', extra_name='scrapy'):
        raise ModuleNotFoundError("No module named 'scrapy'")

    for name in ('first', 'second'):
        assert isinstance(object.__getattribute__(module, name), FailedImport)
