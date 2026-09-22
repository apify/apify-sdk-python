from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import dataclass
from types import ModuleType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Any


@contextmanager
def try_import(module_name: str, *symbol_names: str, extra_name: str) -> Iterator[None]:
    """Context manager to attempt importing symbols into a module.

    If an `ImportError` is raised during the import, the symbols are replaced with `FailedImport` objects, so that
    accessing them later raises the error instead of failing at import time. When the error is a
    `ModuleNotFoundError`, the message also names the optional extra that installs the missing dependency. Other
    import errors, including those raised by a nested guard, keep their message as is.

    This mirrors `crawlee._utils.try_import`, but names the extras of this package rather than Crawlee's.

    Args:
        module_name: The name of the module the symbols are imported into.
        symbol_names: The names of the symbols being imported.
        extra_name: The name of the optional extra that provides the dependency.
    """
    try:
        yield
    except ImportError as exc:
        message = str(exc)
        if isinstance(exc, ModuleNotFoundError):
            message = (
                f"{message}. Install the optional '{extra_name}' extra to use it: pip install 'apify[{extra_name}]'"
            )
        for symbol_name in symbol_names:
            setattr(sys.modules[module_name], symbol_name, FailedImport(message))


def install_import_hook(module_name: str) -> None:
    """Install an import hook for a specified module.

    Args:
        module_name: The name of the module to install the hook for.
    """
    sys.modules[module_name].__class__ = ImportWrapper


@dataclass
class FailedImport:
    """Represent a placeholder for a failed import."""

    message: str
    """The error message associated with the failed import."""


class ImportWrapper(ModuleType):
    """A wrapper class for modules to handle attribute access for failed imports."""

    def __getattribute__(self, name: str) -> Any:
        result = super().__getattribute__(name)

        if isinstance(result, FailedImport):
            raise ImportError(result.message)  # noqa: TRY004

        return result
