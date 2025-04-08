import asyncio
import os
import sys

import pytest
from yarl import URL

from apify import Actor, Configuration


@pytest.mark.skipif(sys.version_info[:3] < (3, 11), reason='asyncio.timeout was introduced in Python 3.11.')
async def test_storage_access_use_reasonable_timeout(server_url: URL) -> None:
    """Test that accessing storages through Apify API through Actor will use client with reasonable timeout.

    This is to prevent situations where for example one `RequestQueue` access through API can block for 360 seconds
    (which is default timeout of the client).

    This test creates situation where first request is for whatever reason handled with very long delay by the server,
    expected behavior is to rather retry early than wait for up to 360 seconds."""

    os.environ['APIFY_TOKEN'] = 'whatever'

    configuration = Configuration.get_global_configuration()
    configuration.api_public_base_url = str(server_url)
    configuration.api_base_url = str(server_url)

    # The reasonable storage related Apify API request timeout expected by the tests.
    expected_timeout = 10
    # Added tolerance for the second request response. Mainly due to the backoff time after first timed out request.
    backoff_tolerance = 2

    async with Actor(configuration=configuration):
        async with asyncio.timeout(expected_timeout + backoff_tolerance):  # type:ignore[attr-defined]  # Test is skipped in older Python versions.
            await Actor.open_dataset(force_cloud=True)
