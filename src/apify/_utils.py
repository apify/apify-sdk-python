from __future__ import annotations

import builtins
import sys
from enum import Enum
from importlib import metadata
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Callable


def get_system_info() -> dict:
    python_version = '.'.join([str(x) for x in sys.version_info[:3]])

    system_info: dict[str, str | bool] = {
        'apify_sdk_version': metadata.version('apify'),
        'apify_client_version': metadata.version('apify-client'),
        'crawlee_version': metadata.version('crawlee'),
        'python_version': python_version,
        'os': sys.platform,
    }

    if is_running_in_ipython():
        system_info['is_running_in_ipython'] = True

    return system_info


def is_running_in_ipython() -> bool:
    return getattr(builtins, '__IPYTHON__', False)


# The order of the rendered API groups is defined in the website/docusaurus.config.js file.
GroupName = Literal[
    'Actor',
    'Charging',
    'Configuration',
    'Event data',
    'Event managers',
    'Events',
    'Request loaders',
    'Storage clients',
    'Storage data',
    'Storages',
]


def docs_group(group_name: GroupName) -> Callable:  # noqa: ARG001
    """Mark a symbol for rendering and grouping in documentation.

    This decorator is used solely for documentation purposes and does not modify the behavior
    of the decorated callable.

    Args:
        group_name: The documentation group to which the symbol belongs.

    Returns:
        The original callable without modification.
    """

    def wrapper(func: Callable) -> Callable:
        return func

    return wrapper


def docs_name(symbol_name: str) -> Callable:  # noqa: ARG001
    """Rename a symbol for documentation rendering.

    This decorator modifies only the displayed name of the symbol in the generated documentation
    and does not affect its runtime behavior.

    Args:
        symbol_name: The name to be used in the documentation.

    Returns:
        The original callable without modification.
    """

    def wrapper(func: Callable) -> Callable:
        return func

    return wrapper


def maybe_extract_enum_member_value(maybe_enum_member: Any) -> Any:
    """Extract the value of an enumeration member if it is an Enum, otherwise return the original value."""
    if isinstance(maybe_enum_member, Enum):
        return maybe_enum_member.value
    return maybe_enum_member
