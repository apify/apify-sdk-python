from __future__ import annotations

import builtins
import sys
from importlib import metadata
from typing import Callable, Literal


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


GroupName = Literal['Classes', 'Abstract classes', 'Data structures', 'Errors', 'Functions']


def docs_group(group_name: GroupName) -> Callable:  # noqa: ARG001
    """Decorator to mark symbols for rendering and grouping in documentation.

    This decorator is used purely for documentation purposes and does not alter the behavior
    of the decorated callable.
    """

    def wrapper(func: Callable) -> Callable:
        return func

    return wrapper


def docs_name(symbol_name: str) -> Callable:  # noqa: ARG001
    """Decorator for renaming symbols in documentation.

    This changes the rendered name of the symbol only in the rendered web documentation.

    This decorator is used purely for documentation purposes and does not alter the behavior
    of the decorated callable.
    """

    def wrapper(func: Callable) -> Callable:
        return func

    return wrapper
