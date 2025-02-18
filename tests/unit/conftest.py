from __future__ import annotations

import asyncio
import inspect
import os
from collections import defaultdict
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Callable, get_type_hints

import pytest

from apify_client import ApifyClientAsync
from apify_shared.consts import ApifyEnvVars
from crawlee import service_locator
from crawlee.configuration import Configuration as CrawleeConfiguration
from crawlee.storage_clients import MemoryStorageClient
from crawlee.storages import _creation_management

import apify._actor

if TYPE_CHECKING:
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
        delattr(apify._actor.Actor, '__wrapped__')
        apify._actor._ActorType._is_any_instance_initialized = False

        # Set the environment variable for the local storage directory to the temporary path.
        monkeypatch.setenv(ApifyEnvVars.LOCAL_STORAGE_DIR, str(tmp_path))

        # Reset the flags in the service locator to indicate that no services are explicitly set. This ensures
        # a clean state, as services might have been set during a previous test and not reset properly.
        service_locator._configuration_was_retrieved = False
        service_locator._storage_client_was_retrieved = False
        service_locator._event_manager_was_retrieved = False

        # Reset the services in the service locator.
        service_locator._configuration = None
        service_locator._event_manager = None
        service_locator._storage_client = None

        # Clear creation-related caches to ensure no state is carried over between tests.
        monkeypatch.setattr(_creation_management, '_cache_dataset_by_id', {})
        monkeypatch.setattr(_creation_management, '_cache_dataset_by_name', {})
        monkeypatch.setattr(_creation_management, '_cache_kvs_by_id', {})
        monkeypatch.setattr(_creation_management, '_cache_kvs_by_name', {})
        monkeypatch.setattr(_creation_management, '_cache_rq_by_id', {})
        monkeypatch.setattr(_creation_management, '_cache_rq_by_name', {})

        # Verify that the test environment was set up correctly.
        assert os.environ.get(ApifyEnvVars.LOCAL_STORAGE_DIR) == str(tmp_path)
        assert service_locator._configuration_was_retrieved is False
        assert service_locator._storage_client_was_retrieved is False
        assert service_locator._event_manager_was_retrieved is False

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


# This class is used to patch the ApifyClientAsync methods to return a fixed value or be replaced with another method.
class ApifyClientAsyncPatcher:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.monkeypatch = monkeypatch
        self.calls: dict[str, dict[str, list[tuple[Any, Any]]]] = defaultdict(lambda: defaultdict(list))

    def patch(
        self,
        method: str,
        submethod: str,
        *,
        return_value: Any = None,
        replacement_method: Callable | None = None,
        is_async: bool | None = None,
    ) -> None:
        """
        Patch a method in ApifyClientAsync.

        Patches a submethod in ApifyClientAsync (e.g. `apify_client_async.user().get`)
        to either return a fixed value, or be replaced with another method.
        The patches will be reverted after the test is over.

        One of `return_value` and `replacement_method` arguments must be specified.

        Args:
            method: Which root method to patch in the ApifyClientAsync.
            submethod: Which submethod to patch in the root method's result.
            return_value: What should the patched method return.
            replacement_method: What method should the original method be replaced by.
            is_async: Whether the return value or replacement method should be wrapped by an async wrapper,
                in order to not break any `await` statements.
                If not passed, it is automatically detected from the type of the method which is being replaced.
        """

        client_method = getattr(ApifyClientAsync, method, None)
        if not client_method:
            raise ValueError(f'ApifyClientAsync does not contain method "{method}"!')

        try:
            # Try to get the return type of the client method using `typing.get_type_hints()`
            client_method_return_type = get_type_hints(client_method)['return']
        except TypeError:
            # There is a known issue with `typing.get_type_hints()` on Python 3.9. It raises a `TypeError`
            # when `|` (Union) is used in the type hint, even with `from __future__ import annotations`. Since we
            # only need the return type, we attempt the following workaround.

            # 1. Create a deep copy of the client method object
            client_method_copied = deepcopy(client_method)

            # 2. Restrict the annotations to only include the return type
            client_method_copied.__annotations__ = {'return': client_method.__annotations__['return']}

            # 3. Try to get the return type again using `typing.get_type_hints()`
            client_method_return_type = get_type_hints(client_method_copied)['return']

            # TODO: Remove this fallback once we drop support for Python 3.9
            # https://github.com/apify/apify-sdk-python/issues/151

        original_submethod = getattr(client_method_return_type, submethod, None)

        if not original_submethod:
            raise ValueError(
                f'apify_client.{client_method_return_type.__name__} does not contain method "{submethod}"!'
            )

        if is_async is None:
            is_async = inspect.iscoroutinefunction(original_submethod)

        if is_async:
            if replacement_method:
                if not inspect.iscoroutinefunction(replacement_method):
                    original_replacement_method = replacement_method

                    async def replacement_method(*args: Any, **kwargs: Any) -> Any:
                        return original_replacement_method(*args, **kwargs)
            else:
                original_return_value = return_value
                return_value = asyncio.Future()
                return_value.set_result(original_return_value)

        if not replacement_method:

            def replacement_method(*_args: Any, **_kwargs: Any) -> Any:
                return return_value

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            self.calls[method][submethod].append((args, kwargs))

            assert replacement_method is not None
            return replacement_method(*args, **kwargs)

        self.monkeypatch.setattr(client_method_return_type, submethod, wrapper, raising=False)

        original_getattr = getattr(ApifyClientAsync, '__getattr__', None)

        def getattr_override(apify_client_instance: Any, attr_name: str) -> Any:
            if attr_name == 'calls':
                return self.calls

            if original_getattr:
                return original_getattr(apify_client_instance, attr_name)

            return object.__getattribute__(apify_client_instance, attr_name)

        self.monkeypatch.setattr(ApifyClientAsync, '__getattr__', getattr_override, raising=False)


@pytest.fixture
def apify_client_async_patcher(monkeypatch: pytest.MonkeyPatch) -> ApifyClientAsyncPatcher:
    return ApifyClientAsyncPatcher(monkeypatch)


@pytest.fixture
def memory_storage_client() -> MemoryStorageClient:
    configuration = CrawleeConfiguration()
    configuration.persist_storage = True
    configuration.write_metadata = True

    return MemoryStorageClient.from_config(configuration)
