from __future__ import annotations

import sys
from types import ModuleType

import pytest

import apify.scrapy
from apify._try_import import install_import_hook, try_import


@pytest.fixture
def guarded_module() -> ModuleType:
    """Create a throwaway module with the import hook installed."""
    module = ModuleType('_test_guarded_module')
    sys.modules[module.__name__] = module
    install_import_hook(module.__name__)
    return module


def test_missing_dependency_names_the_apify_extra(guarded_module: ModuleType) -> None:
    """Test that a missing optional dependency points to the extra of this package, not Crawlee's."""
    with try_import(guarded_module.__name__, 'some_symbol', extra_name='scrapy'):
        raise ModuleNotFoundError("No module named 'scrapy'")

    with pytest.raises(ImportError) as exc_info:
        _ = guarded_module.some_symbol

    assert "pip install 'apify[scrapy]'" in str(exc_info.value)
    assert 'crawlee[scrapy]' not in str(exc_info.value)


def test_other_import_errors_keep_their_message(guarded_module: ModuleType) -> None:
    """Test that import errors other than a missing module are not annotated with an install hint."""
    with try_import(guarded_module.__name__, 'some_symbol', extra_name='scrapy'):
        raise ImportError('Something else went wrong')

    with pytest.raises(ImportError, match=r'^Something else went wrong$'):
        _ = guarded_module.some_symbol


def test_successful_imports_are_untouched(guarded_module: ModuleType) -> None:
    """Test that the guard does not interfere with imports that succeed."""
    with try_import(guarded_module.__name__, 'some_symbol', extra_name='scrapy'):
        guarded_module.some_symbol = 'value'  # ty: ignore[unresolved-attribute]

    assert guarded_module.some_symbol == 'value'


def test_scrapy_integration_exports_are_importable() -> None:
    """Test that the guarded exports of the Scrapy integration resolve with the extra installed."""
    assert apify.scrapy.ApifyScheduler is not None
    assert apify.scrapy.run_scrapy_actor is not None
    assert apify.scrapy.to_apify_request is not None
