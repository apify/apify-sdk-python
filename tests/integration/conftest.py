from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from apify_client import ApifyClientAsync
from apify_shared.consts import ApifyEnvVars
from crawlee import service_locator

import apify._actor
from apify import Actor
from apify.storage_clients import ApifyStorageClient
from apify.storage_clients._apify._alias_resolving import AliasResolver
from apify.storages import RequestQueue

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable
    from pathlib import Path

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


@pytest.fixture
def prepare_test_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Callable[[], None]:
    """Prepare the testing environment by resetting the global state before each test.

    This fixture ensures that the global state of the package is reset to a known baseline before each test runs.
    It also configures a temporary storage directory for test isolation.

    Args:
        monkeypatch: Test utility provided by pytest for patching.
        tmp_path: A unique temporary directory path provided by pytest for test isolation.

    Returns:
        A callable that prepares the test environment.
    """

    def _prepare_test_env() -> None:
        if hasattr(apify._actor.Actor, '__wrapped__'):
            delattr(apify._actor.Actor, '__wrapped__')

        apify._actor.Actor._is_initialized = False

        # Set the environment variable for the local storage directory to the temporary path.
        monkeypatch.setenv(ApifyEnvVars.LOCAL_STORAGE_DIR, str(tmp_path))

        # Reset the services in the service locator.
        service_locator._configuration = None
        service_locator._event_manager = None
        service_locator._storage_client = None
        service_locator.storage_instance_manager.clear_cache()

        # Reset the AliasResolver class state.
        AliasResolver._alias_map = {}
        AliasResolver._alias_init_lock = None

        # Verify that the test environment was set up correctly.
        assert os.environ.get(ApifyEnvVars.LOCAL_STORAGE_DIR) == str(tmp_path)

    return _prepare_test_env


@pytest.fixture(params=['single', 'shared'])
async def request_queue_apify(
    apify_token: str, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> AsyncGenerator[RequestQueue]:
    """Create an instance of the Apify request queue on the platform and drop it when the test is finished."""
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_token)

    async with Actor:
        rq = await RequestQueue.open(storage_client=ApifyStorageClient(request_queue_access=request.param))
        yield rq
        await rq.drop()


@pytest.fixture(autouse=True)
def _isolate_test_environment(prepare_test_env: Callable[[], None]) -> None:
    """Isolate the testing environment by resetting global state before each test.

    This fixture ensures that each test starts with a clean slate and that any modifications during the test
    do not affect subsequent tests. It runs automatically for all tests.

    Args:
        prepare_test_env: Fixture to prepare the environment before each test.
    """
    prepare_test_env()
