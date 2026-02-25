from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, TypeVar, cast

from crawlee._utils.crypto import crypto_random_object_id

from apify import Actor

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

T = TypeVar('T')


async def call_with_exp_backoff(fn: Callable[[], Awaitable[T]], *, max_retries: int = 3) -> T:
    """Call an async callable with exponential backoff retries until it returns a truthy value.

    In shared request queue mode, there is a propagation delay before newly added, reclaimed, or handled requests
    become visible in the API (see https://github.com/apify/apify-sdk-python/issues/808). This helper retries with
    exponential backoff to handle that delay in integration tests.
    """
    result = None
    for attempt in range(max_retries):
        result = await fn()
        if result:
            return result
        delay = 2**attempt
        Actor.log.info(f'{fn} returned {result!r}, retrying in {delay}s (attempt {attempt + 1}/{max_retries})')
        await asyncio.sleep(delay)
    return cast('T', result)


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
