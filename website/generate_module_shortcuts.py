#!/usr/bin/env python3

from __future__ import annotations

import importlib
import inspect
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType
    from typing import Any


def get_members(module: ModuleType, predicate: Callable[[Any], bool]) -> list[tuple[str, Any]]:
    """Like `inspect.getmembers`, but skip attributes that raise `ImportError` because an optional extra is missing."""
    members = []
    for name in dir(module):
        try:
            value = getattr(module, name)
        except ImportError:
            continue
        if predicate(value):
            members.append((name, value))
    return members


def get_module_shortcuts(module: ModuleType, parent_classes: list | None = None) -> dict:
    """Traverse a module and its submodules to identify and register shortcuts for classes."""
    shortcuts = {}

    if parent_classes is None:
        parent_classes = []

    parent_module_name = '.'.join(module.__name__.split('.')[:-1])
    module_classes = []

    for classname, cls in get_members(module, inspect.isclass):
        module_classes.append(cls)
        if cls in parent_classes:
            shortcuts[f'{module.__name__}.{classname}'] = f'{parent_module_name}.{classname}'

    for _, submodule in get_members(module, inspect.ismodule):
        if submodule.__name__.startswith('apify'):
            shortcuts.update(get_module_shortcuts(submodule, module_classes))

    return shortcuts


def resolve_shortcuts(shortcuts: dict) -> None:
    """Resolve linked shortcuts.

    For example, if there are shortcuts A -> B and B -> C, resolve them to A -> C.
    """
    for source, target in shortcuts.items():
        while target in shortcuts:
            shortcuts[source] = shortcuts[target]
            target = shortcuts[target]  # noqa: PLW2901


shortcuts = {}
for module_name in ['apify', 'apify_client', 'apify_shared']:
    try:
        module = importlib.import_module(module_name)
        module_shortcuts = get_module_shortcuts(module)
        shortcuts.update(module_shortcuts)
    except ModuleNotFoundError:
        pass

resolve_shortcuts(shortcuts)

with open('module_shortcuts.json', 'w', encoding='utf-8') as shortcuts_file:
    json.dump(shortcuts, shortcuts_file, indent=4, sort_keys=True)
