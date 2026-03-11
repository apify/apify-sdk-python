from __future__ import annotations

import asyncio
import builtins
import inspect
import sys
from collections.abc import Callable
from contextlib import asynccontextmanager
from enum import Enum
from functools import wraps
from importlib import metadata
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

T = TypeVar('T', bound=Callable[..., Any])


def ensure_context(attribute_name: str) -> Callable[[T], T]:
    """Create a decorator that ensures the context manager is initialized before executing the method.

    The decorator checks if the calling instance has the specified attribute and verifies that it is set to `True`.
    If the instance is inactive, it raises a `RuntimeError`. Works for both synchronous and asynchronous methods.

    Args:
        attribute_name: The name of the boolean attribute to check on the instance.

    Returns:
        A decorator that wraps methods with context checking.
    """

    def decorator(method: T) -> T:
        @wraps(method)
        def sync_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            if not getattr(self, attribute_name, False):
                raise RuntimeError(f'The {self.__class__.__name__} is not active. Use it within the context.')

            return method(self, *args, **kwargs)

        @wraps(method)
        async def async_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            if not getattr(self, attribute_name, False):
                raise RuntimeError(f'The {self.__class__.__name__} is not active. Use it within the async context.')

            return await method(self, *args, **kwargs)

        return cast('T', async_wrapper if inspect.iscoroutinefunction(method) else sync_wrapper)

    return decorator


def get_system_info() -> dict:
    python_version = '.'.join([str(x) for x in sys.version_info[:3]])

    system_info: dict[str, str | bool] = {
        'apify_sdk_version': metadata.version('apify'),
        'apify_client_version': metadata.version('apify-client'),
        'crawlee_version': metadata.version('crawlee'),
        'python_version': python_version,
        'os': sys.platform,
    }

    system_info['is_running_in_ipython'] = is_running_in_ipython()

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


class ReentrantLock:
    """A reentrant lock implementation for asyncio using asyncio.Lock."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._owner: asyncio.Task | None = None

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[None]:
        """Acquire the lock if it's not already owned by the current task, otherwise proceed without acquiring."""
        me = asyncio.current_task()
        if self._owner is me:
            yield
            return
        async with self._lock:
            self._owner = me
            try:
                yield
            finally:
                self._owner = None
