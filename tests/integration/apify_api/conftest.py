from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from apify_shared.consts import ApifyEnvVars
from crawlee import service_locator

import apify._actor
from apify.storage_clients._apify._alias_resolving import AliasResolver

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


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
        # Reset the Actor class state.
        apify._actor.Actor.__wrapped__.__class__._is_any_instance_initialized = False  # type: ignore[attr-defined]
        apify._actor.Actor.__wrapped__.__class__._is_rebooting = False  # type: ignore[attr-defined]
        delattr(apify._actor.Actor, '__wrapped__')

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


@pytest.fixture(autouse=True)
def _isolate_test_environment(prepare_test_env: Callable[[], None]) -> None:
    """Isolate the testing environment by resetting global state before and after each test.

    This fixture ensures that each test starts with a clean slate and that any modifications during the test
    do not affect subsequent tests. It runs automatically for all tests.

    Args:
        prepare_test_env: Fixture to prepare the environment before each test.
    """

    prepare_test_env()
