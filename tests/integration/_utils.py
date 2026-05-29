from __future__ import annotations

import asyncio
import inspect
import logging
import time
from typing import TYPE_CHECKING, TypeVar, cast, overload

from crawlee._utils.crypto import crypto_random_object_id

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

T = TypeVar('T')


async def _maybe_await(value: Awaitable[T] | T) -> T:
    """Await `value` if it is awaitable, otherwise return it unchanged.

    Lets `call_with_exp_backoff` and `poll_until_condition` accept both sync and async callables.
    """
    if inspect.isawaitable(value):
        return await cast('Awaitable[T]', value)
    return cast('T', value)


@overload
async def call_with_exp_backoff(
    fn: Callable[[], Awaitable[T]],
    condition: Callable[[T], bool] = ...,
    *,
    max_retries: int = ...,
    base_delay: float = ...,
) -> T: ...
@overload
async def call_with_exp_backoff(
    fn: Callable[[], T],
    condition: Callable[[T], bool] = ...,
    *,
    max_retries: int = ...,
    base_delay: float = ...,
) -> T: ...
async def call_with_exp_backoff(
    fn: Callable[[], Awaitable[T] | T],
    condition: Callable[[T], bool] = bool,
    *,
    max_retries: int = 5,
    base_delay: float = 1.0,
) -> T:
    """Call `fn`, retrying with exponential backoff until `condition(result)` is True.

    Calls `fn` and checks whether `condition` holds for its result. If it does not, `fn` is retried up to
    `max_retries` times, sleeping `base_delay * 2 ** attempt` seconds before each retry. The last result is
    returned regardless of whether the condition was ever satisfied, so the caller can run its own assertion.

    This is useful for eventually-consistent APIs where a freshly added, reclaimed, or handled item may take a
    moment to become visible (see https://github.com/apify/apify-sdk-python/issues/808). The default condition
    checks for a truthy result. Pass `max_retries=0` to call `fn` exactly once without any retries.

    Unlike `poll_until_condition`, the delay between attempts grows exponentially rather than staying constant.
    """
    result = await _maybe_await(fn())
    for attempt in range(max_retries):
        if condition(result):
            return result
        delay = base_delay * 2**attempt
        logger.info(
            'Condition not met for %r, retrying in %ss (attempt %d/%d).', result, delay, attempt + 1, max_retries
        )
        await asyncio.sleep(delay)
        result = await _maybe_await(fn())
    return result


@overload
async def poll_until_condition(
    fn: Callable[[], Awaitable[T]],
    condition: Callable[[T], bool] = ...,
    *,
    timeout: float = ...,
    poll_interval: float = ...,
) -> T: ...
@overload
async def poll_until_condition(
    fn: Callable[[], T],
    condition: Callable[[T], bool] = ...,
    *,
    timeout: float = ...,
    poll_interval: float = ...,
) -> T: ...
async def poll_until_condition(
    fn: Callable[[], Awaitable[T] | T],
    condition: Callable[[T], bool] = bool,
    *,
    timeout: float = 60,
    poll_interval: float = 5,
) -> T:
    """Poll `fn` until `condition(result)` is True or the timeout expires.

    Polls `fn` at `poll_interval`-second intervals until `condition` is satisfied or `timeout` seconds have elapsed.
    Returns the last polled result regardless of whether the condition was met, so the caller can run its own
    assertion. The default condition checks for a truthy result.

    Use this instead of a fixed `asyncio.sleep` when waiting for eventually-consistent state (e.g. request queue
    stats) that may take a variable amount of time to propagate. Unlike `call_with_exp_backoff`, the interval
    between polls stays constant.
    """
    deadline = time.monotonic() + timeout
    result = await _maybe_await(fn())
    while not condition(result):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        await asyncio.sleep(min(poll_interval, remaining))
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
