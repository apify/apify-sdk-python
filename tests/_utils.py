from __future__ import annotations

import asyncio
import inspect
import time
from typing import TYPE_CHECKING, TypeVar, cast, overload

from crawlee._utils.crypto import crypto_random_object_id

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

T = TypeVar('T')


async def _maybe_await(value: Awaitable[T] | T) -> T:
    """Await `value` if it is awaitable, otherwise return it unchanged.

    Lets `poll_until_condition` accept both sync and async callables.
    """
    if inspect.isawaitable(value):
        return await cast('Awaitable[T]', value)
    return cast('T', value)


@overload
async def poll_until_condition(
    fn: Callable[[], Awaitable[T]],
    condition: Callable[[T], bool] = ...,
    *,
    timeout: float = ...,
    poll_interval: float = ...,
    backoff_factor: float = ...,
) -> T: ...
@overload
async def poll_until_condition(
    fn: Callable[[], T],
    condition: Callable[[T], bool] = ...,
    *,
    timeout: float = ...,
    poll_interval: float = ...,
    backoff_factor: float = ...,
) -> T: ...
async def poll_until_condition(
    fn: Callable[[], Awaitable[T] | T],
    condition: Callable[[T], bool] = bool,
    *,
    timeout: float = 5,
    poll_interval: float = 1,
    backoff_factor: float = 1,
) -> T:
    """Poll `fn` until `condition(result)` is True or the timeout expires.

    Polls `fn` at `poll_interval`-second intervals until `condition` is satisfied or `timeout` seconds have elapsed.
    Returns the last polled result regardless of whether the condition was met, so the caller can run its own
    assertion. The default condition checks for a truthy result. Pass `timeout=0` to call `fn` exactly once.

    Use this instead of a fixed `asyncio.sleep` when waiting for eventually-consistent state (e.g. a freshly
    created resource appearing in a listing) that may take a variable amount of time to propagate. For highly
    variable wait times (e.g. an Actor run container starting up), pass `backoff_factor` > 1 to multiply the
    interval after each poll, covering a long timeout with few calls.
    """
    deadline = time.monotonic() + timeout
    delay = poll_interval
    result = await _maybe_await(fn())
    while not condition(result):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        await asyncio.sleep(min(delay, remaining))
        delay *= backoff_factor
        result = await _maybe_await(fn())
    return result


def generate_unique_resource_name(label: str) -> str:
    """Generates a unique resource name, which will contain the given label."""
    name_template = 'python-sdk-tests-{}-generated-{}'
    template_length = len(name_template.format('', ''))
    api_name_limit = 63
    generated_random_id_length = 8
    label_length_limit = api_name_limit - template_length - generated_random_id_length

    label = label.replace('_', '-')
    assert len(label) <= label_length_limit, f'Max label length is {label_length_limit}, but got {len(label)}'

    return name_template.format(label, crypto_random_object_id(generated_random_id_length))
