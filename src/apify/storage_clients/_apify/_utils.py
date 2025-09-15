from __future__ import annotations

from typing import TYPE_CHECKING

from apify_client import ApifyClientAsync

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from apify import Configuration


def create_apify_client(configuration: Configuration) -> ApifyClientAsync:
    """Create and return an ApifyClientAsync instance using the provided configuration."""
    token = configuration.token
    if not token:
        raise ValueError(f'Apify storage client requires a valid token in Configuration (token={token}).')

    api_url = configuration.api_base_url
    if not api_url:
        raise ValueError(f'Apify storage client requires a valid API URL in Configuration (api_url={api_url}).')

    api_public_base_url = configuration.api_public_base_url
    if not api_public_base_url:
        raise ValueError(
            'Apify storage client requires a valid API public base URL in Configuration '
            f'(api_public_base_url={api_public_base_url}).'
        )

    # Create Apify client with the provided token and API URL.
    return ApifyClientAsync(
        token=token,
        api_url=api_url,
        api_public_url=api_public_base_url,
        max_retries=8,
        min_delay_between_retries_millis=500,
        timeout_secs=360,
    )


async def resolve_storage_id(
    id: str | None, name: str | None, default_id: str, id_getter: Coroutine[None, None, str]
) -> str:
    """Resolve and return the storage ID from arguments."""
    try:
        match (id, name):
            case (None, None):
                # If both id and name are None, try to get the default storage ID from environment variables.
                # The default storage ID environment variable is set by the Apify platform. It also contains
                # a new storage ID after Actor's reboot or migration.
                id = default_id
            case (None, name):
                # If only name is provided, get or create the storage by name.
                id = await id_getter
            case (_, None):
                # If only id is provided, use it.
                pass
            case (_, _):
                # If both id and name are provided, raise an error.
                raise ValueError('Only one of "id" or "name" can be specified, not both.')
        if id is None:
            raise RuntimeError('Unreachable code')
        return id
    finally:
        id_getter.close()
