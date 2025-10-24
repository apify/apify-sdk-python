from __future__ import annotations

import os

import pytest

from apify_client import ApifyClientAsync

_TOKEN_ENV_VAR = 'APIFY_TEST_USER_API_TOKEN'
_API_URL_ENV_VAR = 'APIFY_INTEGRATION_TESTS_API_URL'


@pytest.fixture(scope='session')
def apify_token() -> str:
    api_token = os.getenv(_TOKEN_ENV_VAR)

    if not api_token:
        raise RuntimeError(f'{_TOKEN_ENV_VAR} environment variable is missing, cannot run tests!')

    return api_token


@pytest.fixture(scope='session')
def apify_client_async(apify_token: str) -> ApifyClientAsync:
    """Create an instance of the ApifyClientAsync."""
    api_url = os.getenv(_API_URL_ENV_VAR)

    return ApifyClientAsync(apify_token, api_url=api_url)
